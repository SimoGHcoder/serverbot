"""Read recent DIUN logs through the Docker API."""
from modules import docker_mgr


def get_diun_logs(lines: int = 40) -> str:
    return docker_mgr.get_logs("diun", lines=lines)
