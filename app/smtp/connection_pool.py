"""
SMTP Connection Pool
Efficient connection reuse for high-volume sending
"""
import smtplib
import ssl
import threading
import queue
import time
import logging
from typing import Optional, Dict
from collections import defaultdict

logger = logging.getLogger(__name__)


class SMTPConnection:
    """Wrapper for SMTP connection with metadata"""
    
    def __init__(self, server: str, port: int = 25):
        self.server = server
        self.port = port
        self.connection: Optional[smtplib.SMTP] = None
        self.created_at = time.time()
        self.last_used = time.time()
        self.use_count = 0
        self.tls_enabled = False
    
    def connect(self, hostname: str = 'mail.sendbaba.com') -> bool:
        """Establish connection"""
        try:
            self.connection = smtplib.SMTP(self.server, self.port, timeout=30)
            self.connection.ehlo(hostname)
            
            # Try TLS
            if self.connection.has_extn('STARTTLS'):
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                self.connection.starttls(context=context)
                self.connection.ehlo(hostname)
                self.tls_enabled = True
            
            self.created_at = time.time()
            self.last_used = time.time()
            logger.debug(f"Connected to {self.server}:{self.port} (TLS: {self.tls_enabled})")
            return True
        except Exception as e:
            logger.warning(f"Connection failed to {self.server}: {e}")
            return False
    
    def is_alive(self) -> bool:
        """Check if connection is still alive"""
        if not self.connection:
            return False
        try:
            self.connection.noop()
            return True
        except:
            return False
    
    def send(self, from_addr: str, to_addrs: list, message: bytes) -> bool:
        """Send email using this connection"""
        if not self.connection:
            return False
        try:
            self.connection.sendmail(from_addr, to_addrs, message)
            self.last_used = time.time()
            self.use_count += 1
            return True
        except Exception as e:
            logger.warning(f"Send failed on {self.server}: {e}")
            return False
    
    def close(self):
        """Close connection"""
        if self.connection:
            try:
                self.connection.quit()
            except:
                pass
            self.connection = None


class SMTPConnectionPool:
    """Pool of SMTP connections per MX server"""
    
    def __init__(self, max_connections: int = 10, max_age: int = 300):
        self.max_connections = max_connections
        self.max_age = max_age  # Max connection age in seconds
        self.pools: Dict[str, queue.Queue] = defaultdict(lambda: queue.Queue(maxsize=max_connections))
        self.locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)
        self.stats = defaultdict(lambda: {'created': 0, 'reused': 0, 'failed': 0})
    
    def get_connection(self, server: str, port: int = 25) -> Optional[SMTPConnection]:
        """Get a connection from pool or create new one"""
        pool_key = f"{server}:{port}"
        
        with self.locks[pool_key]:
            # Try to get existing connection
            pool = self.pools[pool_key]
            
            while not pool.empty():
                try:
                    conn = pool.get_nowait()
                    
                    # Check if connection is still valid
                    if time.time() - conn.created_at > self.max_age:
                        conn.close()
                        continue
                    
                    if conn.is_alive():
                        self.stats[pool_key]['reused'] += 1
                        logger.debug(f"Reusing connection to {server}")
                        return conn
                    else:
                        conn.close()
                except queue.Empty:
                    break
            
            # Create new connection
            conn = SMTPConnection(server, port)
            if conn.connect():
                self.stats[pool_key]['created'] += 1
                return conn
            else:
                self.stats[pool_key]['failed'] += 1
                return None
    
    def return_connection(self, conn: SMTPConnection):
        """Return connection to pool"""
        if not conn or not conn.connection:
            return
        
        pool_key = f"{conn.server}:{conn.port}"
        pool = self.pools[pool_key]
        
        # Check if connection is worth keeping
        if time.time() - conn.created_at > self.max_age:
            conn.close()
            return
        
        if conn.use_count > 100:  # Max 100 emails per connection
            conn.close()
            return
        
        try:
            pool.put_nowait(conn)
        except queue.Full:
            conn.close()
    
    def close_all(self):
        """Close all connections"""
        for pool_key, pool in self.pools.items():
            while not pool.empty():
                try:
                    conn = pool.get_nowait()
                    conn.close()
                except queue.Empty:
                    break
    
    def get_stats(self) -> dict:
        """Get pool statistics"""
        return dict(self.stats)


# Global connection pool
smtp_pool = SMTPConnectionPool(max_connections=10, max_age=300)
