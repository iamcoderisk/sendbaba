"""
Force IPv4 for SMTP connections to avoid Gmail IPv6 PTR issues
"""
import socket

# Monkey-patch to prefer IPv4
_original_getaddrinfo = socket.getaddrinfo

def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """Force IPv4 by filtering out IPv6 results"""
    results = _original_getaddrinfo(host, port, family, type, proto, flags)
    # Prefer IPv4 (AF_INET = 2)
    ipv4_results = [r for r in results if r[0] == socket.AF_INET]
    return ipv4_results if ipv4_results else results

socket.getaddrinfo = _ipv4_getaddrinfo
