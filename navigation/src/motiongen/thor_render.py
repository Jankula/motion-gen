"""AI2-THOR rendering: shared by scripts/export_procthor.py and the render server. Needs a GPU with Vulkan.

The render server keeps one simulator open for a whole episode, so the agent gets a fresh ego
view after every walk without paying the simulator's start-up each time:

    python -m motiongen.thor_render serve <episode.yaml> <run_dir>

It listens on a free localhost port and writes the port number to <run_dir>/render.port (a
Unix socket path inside a run folder can exceed the 108-character limit). Each request (one
JSON line) gives the world state as world.py has it:
where the person stands and faces, what is open, what is carried and where moved objects
are. The server makes the simulator match it, renders one ego view into <run_dir>/renders/<name>/
(rgb.png, ids.png, objects.json, camera.json, like the exported views) and answers with the
directory. run_episode.py starts and stops the server; cli.py's goto is the client.
"""

import argparse
import json
import os
import socket
import socketserver
import subprocess
import sys
import time
from pathlib import Path

import yaml

from . import procthor
from .navigation import REPO_ROOT

WIDTH, HEIGHT = 800, 600
# The top view covers the whole house, so it needs more pixels for cups and cutlery to show.
TOP_WIDTH, TOP_HEIGHT = 1600, 1200
# Somewhere outside any house, so the simulator's robot isn't in the top view.
AWAY = {"x": -50.0, "y": 0.95, "z": -50.0}
FIELD_OF_VIEW = 90
# Degrees below level for the ego views, so tabletops are in view.
EGO_HORIZON = 15
EGO_TURNS = {"front": 0, "left": 90, "back": 180, "right": 270}
# "cloud" renders headless (CloudRendering); "linux64" through an X display (WSL).
PLATFORM = "cloud"
PORT_FILE = "render.port"
SERVER_START_TIMEOUT = 300
RENDER_TIMEOUT = 60


def load_house(split, index):
    import prior

    return prior.load_dataset("procthor-10k")[split][index]


def start_controller(house, platform=None):
    from ai2thor.controller import Controller
    from ai2thor.platform import CloudRendering, Linux64

    if (platform or PLATFORM) == "linux64":
        options = {"platform": Linux64, "x_display": os.environ.get("DISPLAY", ":0").lstrip(":")}
    else:
        options = {"platform": CloudRendering}
    return Controller(
        scene=house, renderInstanceSegmentation=True,
        width=WIDTH, height=HEIGHT, fieldOfView=FIELD_OF_VIEW, **options,
    )


def objects_by_id(controller):
    return {o["objectId"]: o for o in controller.last_event.metadata["objects"]}


def set_openness(controller, thor_id, openness):
    action = "OpenObject" if openness > 0 else "CloseObject"
    extra = {"openness": openness} if openness > 0 else {}
    event = controller.step(action=action, objectId=thor_id, forceAction=True, **extra)
    return event.metadata["lastActionSuccess"]


def close_all(controller):
    for obj in objects_by_id(controller).values():
        if obj.get("openable") and obj.get("isOpen"):
            set_openness(controller, obj["objectId"], 0.0)


def is_door(obj):
    return obj["objectType"] in procthor.DOOR_TYPES or obj["objectId"].startswith("door")


def top_view(controller):
    """Add an orthographic camera above the house; returns (rgb, segmentation, camera).

    The robot is moved out of the house first; ego views teleport it back afterwards.
    """
    event = controller.step(action="Teleport", position=AWAY, forceAction=True)
    if not event.metadata["lastActionSuccess"]:
        print(f"warning: could not move the robot out of the top view: {event.metadata['errorMessage']}")
    controller.step(action="ChangeResolution", x=TOP_WIDTH, y=TOP_HEIGHT)
    camera = controller.step(action="GetMapViewCameraProperties").metadata["actionReturn"]
    event = controller.step(action="AddThirdPartyCamera", **camera, skyboxColor="white")
    frames = event.third_party_camera_frames[-1], event.third_party_instance_segmentation_frames[-1]
    controller.step(action="ChangeResolution", x=WIDTH, y=HEIGHT)
    return *frames, camera


def ego_view(controller, position, heading, agent_y):
    """Stand the robot at position facing heading; returns (rgb, segmentation, camera)."""
    x, y = position
    event = controller.step(
        action="Teleport", position={"x": x, "y": agent_y, "z": y},
        rotation={"x": 0, "y": procthor.heading_to_unity_yaw(heading), "z": 0},
        horizon=EGO_HORIZON, standing=True, forceAction=True,
    )
    if not event.metadata["lastActionSuccess"]:
        raise RuntimeError(f"teleport failed: {event.metadata['errorMessage']}")
    camera = {"position": [x, y], "heading": heading, "horizon": EGO_HORIZON, "field_of_view": FIELD_OF_VIEW}
    return event.frame, event.instance_segmentation_frame, camera


def save_view(directory, name, rgb, segmentation, color_to_thor_id, ours, camera):
    from PIL import Image

    directory.mkdir(parents=True, exist_ok=True)
    objects, ids_image = procthor.view_objects(segmentation, color_to_thor_id, ours)
    Image.fromarray(rgb).save(directory / "rgb.png")
    Image.fromarray(ids_image).save(directory / "ids.png")
    (directory / "objects.json").write_text(json.dumps({"name": name, "objects": objects}, indent=1))
    (directory / "camera.json").write_text(json.dumps(camera, indent=2))


def color_lookup(controller):
    """Segmentation colour -> objectId, with folded parts mapped to the object they belong to."""
    folded = {o["objectId"] for o in controller.last_event.metadata["objects"] if procthor.is_folded_part(o)}
    return {
        tuple(int(v) for v in color): procthor.whole_object_id(thor_id) if thor_id in folded else thor_id
        for color, thor_id in controller.last_event.color_to_object_id.items()
    }


# --- the render server ----------------------------------------------------------------------

class Renderer:
    """One simulator for one episode, brought in line with world.py's state before each render."""

    def __init__(self, episode_path, out_dir):
        self.episode = yaml.safe_load(Path(episode_path).read_text())
        scene = yaml.safe_load((REPO_ROOT / self.episode["scene"]).read_text())
        self.ours = {o["thor_id"]: o["id"] for o in scene["objects"] if "thor_id" in o}
        self.thor_of = {v: k for k, v in self.ours.items()}
        self.out_dir = Path(out_dir)
        source = scene["source"]
        self.controller = start_controller(load_house(source["split"], source["index"]))
        close_all(self.controller)
        self.open = set()
        for obj_id in self.episode.get("opened", ()):
            if set_openness(self.controller, self.thor_of[obj_id], 1.0):
                self.open.add(obj_id)
        self.agent_y = self.controller.last_event.metadata["agent"]["position"]["y"]
        # Offset from an object's pivot to its box centre, for putting the box centre where world.py says.
        self.offset, self.rotation = {}, {}
        for thor_id, obj in objects_by_id(self.controller).items():
            center, pivot = obj["axisAlignedBoundingBox"]["center"], obj["position"]
            self.offset[thor_id] = {k: center[k] - pivot[k] for k in ("x", "y", "z")}
            self.rotation[thor_id] = obj["rotation"]
        self.disabled = set()
        self.placed = {}

    def _step(self, **action):
        try:
            event = self.controller.step(**action)
        except Exception as error:  # noqa: BLE001 - the simulator rejects bad arguments with exceptions
            return False, f"{type(error).__name__}: {error}"
        return event.metadata["lastActionSuccess"], event.metadata.get("errorMessage")

    def apply(self, opened, removed, moved):
        warnings = []
        for obj_id in sorted(set(opened) ^ self.open):
            if obj_id not in self.thor_of:
                continue
            if set_openness(self.controller, self.thor_of[obj_id], 1.0 if obj_id in opened else 0.0):
                self.open ^= {obj_id}
            else:
                warnings.append(f"could not {'open' if obj_id in opened else 'close'} {obj_id}")
        # Carried things are hidden (the view is the person's own); put-down things come back.
        for obj_id in sorted(self.disabled - set(removed)):
            ok, error = self._step(action="EnableObject", objectId=self.thor_of[obj_id])
            if ok:
                self.disabled.discard(obj_id)
            else:
                warnings.append(f"could not show {obj_id} again: {error}")
        for obj_id, center in sorted(moved.items()):
            if obj_id not in self.thor_of or obj_id in removed or self.placed.get(obj_id) == center:
                continue
            thor_id = self.thor_of[obj_id]
            offset = self.offset.get(thor_id, {"x": 0.0, "y": 0.0, "z": 0.0})
            position = {"x": center[0] - offset["x"], "y": center[2] - offset["y"], "z": center[1] - offset["z"]}
            rotation = self.rotation.get(thor_id, {"x": 0.0, "y": 0.0, "z": 0.0})
            ok, error = self._step(action="TeleportObject", objectId=thor_id, position=position, rotation=rotation,
                                   forceAction=True, forceKinematic=True)
            if not ok:
                ok, error = self._step(action="PlaceObjectAtPoint", objectId=thor_id, position=position)
            if ok:
                self.placed[obj_id] = center
            else:
                warnings.append(f"could not move {obj_id}: {error}")
        for obj_id in sorted(set(removed) - self.disabled):
            if obj_id not in self.thor_of:
                continue
            ok, error = self._step(action="DisableObject", objectId=self.thor_of[obj_id])
            if ok:
                self.disabled.add(obj_id)
            else:
                warnings.append(f"could not hide {obj_id}: {error}")
        return warnings

    def render(self, request):
        started = time.time()
        warnings = self.apply(request.get("opened", []), request.get("removed", []), request.get("moved", {}))
        rgb, segmentation, camera = ego_view(self.controller, request["position"], request["heading"], self.agent_y)
        directory = self.out_dir / request["name"]
        save_view(directory, request["name"], rgb, segmentation, color_lookup(self.controller), self.ours, camera)
        return {"view": str(directory), "warnings": warnings, "seconds": round(time.time() - started, 2)}


def serve(episode_path, run_dir, out_dir=None):
    run_dir = Path(run_dir)
    port_file = run_dir / PORT_FILE
    out_dir = Path(out_dir) if out_dir else run_dir / "renders"
    started = time.time()
    renderer = Renderer(episode_path, out_dir)
    startup = round(time.time() - started, 1)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            request = json.loads(self.rfile.readline())
            if request.get("command") == "stop":
                self.wfile.write(b'{"stopping": true}\n')
                self.server.stopping = True
                return
            if request.get("command") == "ping":
                reply = {"ready": True, "startup_seconds": startup}
            else:
                try:
                    reply = renderer.render(request)
                except Exception as error:  # noqa: BLE001 - report it to the client, keep serving
                    reply = {"error": f"{type(error).__name__}: {error}"}
            self.wfile.write((json.dumps(reply) + "\n").encode())

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        server.stopping = False
        port = server.server_address[1]
        port_file.write_text(str(port))
        print(f"render server ready after {startup} s on port {port}", flush=True)
        while not server.stopping:
            server.handle_request()
    renderer.controller.stop()
    port_file.unlink(missing_ok=True)


def server_port(run_dir):
    """The port of the run's render server, or None if none is running."""
    try:
        return int((Path(run_dir) / PORT_FILE).read_text())
    except (OSError, ValueError):
        return None


def request(port, payload, timeout=RENDER_TIMEOUT):
    """Send one request to the render server and return its reply."""
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as client:
        client.settimeout(timeout)
        client.sendall((json.dumps(payload) + "\n").encode())
        data = b""
        while not data.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
    return json.loads(data)


def start_server(episode_path, run_dir, platform=None):
    """Start the server for an episode; returns (process, startup seconds) or (None, reason)."""
    run_dir = Path(run_dir)
    (run_dir / PORT_FILE).unlink(missing_ok=True)
    with open(run_dir / "render_server.log", "w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "motiongen.thor_render", "serve", str(episode_path), str(run_dir),
             "--platform", platform or PLATFORM],
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        )
    deadline = time.time() + SERVER_START_TIMEOUT
    while time.time() < deadline:
        if process.poll() is not None:
            return None, f"render server exited (code {process.returncode}); see render_server.log"
        port = server_port(run_dir)
        if port is not None:
            try:
                reply = request(port, {"command": "ping"}, timeout=10)
                return process, reply.get("startup_seconds")
            except (OSError, ValueError):
                pass
        time.sleep(0.5)
    process.kill()
    return None, "render server did not start in time"


def stop_server(process, run_dir):
    if process is None:
        return
    port = server_port(run_dir)
    try:
        if port is not None:
            request(port, {"command": "stop"}, timeout=10)
        process.wait(timeout=60)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        process.kill()
    (Path(run_dir) / PORT_FILE).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(prog="python -m motiongen.thor_render")
    commands = parser.add_subparsers(dest="command", required=True)
    serve_parser = commands.add_parser("serve", help="keep a simulator open for one episode")
    serve_parser.add_argument("episode")
    serve_parser.add_argument("run_dir", help="the run folder: gets render.port and renders/")
    serve_parser.add_argument("--out", help="where renders go (default: <run_dir>/renders)")
    serve_parser.add_argument("--platform", choices=["cloud", "linux64"], default="cloud")
    args = parser.parse_args()
    global PLATFORM
    PLATFORM = args.platform
    serve(args.episode, args.run_dir, args.out)


if __name__ == "__main__":
    main()
