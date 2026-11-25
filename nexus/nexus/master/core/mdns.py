"""mDNS (zeroconf) advertisement for LAN discovery."""
from __future__ import annotations

import socket
from typing import Optional

from nexus.shared.logging import get_logger
from nexus.shared.protocol import SERVICE_TYPE

log = get_logger("mdns")


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


class MdnsAdvertiser:
    def __init__(self, port: int, name: str = "nexus-master") -> None:
        self.port = port
        self.name = name
        self.zc = None
        self.info = None

    def start_in_background(self) -> None:
        """Advertise from a daemon thread so multicast issues never block startup."""
        import threading

        threading.Thread(target=self.start, name="nexus-mdns", daemon=True).start()

    def start(self) -> None:
        try:
            from zeroconf import ServiceInfo, Zeroconf

            ip = local_ip()
            self.info = ServiceInfo(
                SERVICE_TYPE,
                f"{self.name}.{SERVICE_TYPE}",
                addresses=[socket.inet_aton(ip)],
                port=self.port,
                properties={"role": "master", "version": "0.1.0"},
                server=f"{self.name}.local.",
            )
            self.zc = Zeroconf()
            self.zc.register_service(self.info)
            log.info("mDNS advertised %s at %s:%s", self.name, ip, self.port)
        except Exception as exc:  # noqa: BLE001
            log.warning("mDNS advertise unavailable: %s", exc)
            self.zc = None

    def stop(self) -> None:
        try:
            if self.zc and self.info:
                self.zc.unregister_service(self.info)
                self.zc.close()
        except Exception:
            pass
        self.zc = None


def discover_masters(timeout: float = 4.0) -> list[dict]:
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except Exception as exc:  # noqa: BLE001
        log.warning("zeroconf not available: %s", exc)
        return []

    found: dict[str, dict] = {}

    class Listener:
        def add_service(self, zc, type_, name):
            info = zc.get_service_info(type_, name)
            if not info:
                return
            addresses = [socket.inet_ntoa(a) for a in info.addresses if len(a) == 4]
            found[name] = {
                "name": name,
                "addresses": addresses,
                "port": info.port,
                "properties": {
                    k.decode(): (v.decode() if v else "") for k, v in (info.properties or {}).items()
                },
            }

        def update_service(self, zc, type_, name):
            self.add_service(zc, type_, name)

        def remove_service(self, zc, type_, name):
            found.pop(name, None)

    import time

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, SERVICE_TYPE, Listener())
        time.sleep(timeout)
    finally:
        zc.close()
    return list(found.values())
