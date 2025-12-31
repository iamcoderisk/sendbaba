"""
SENDBABA EMAIL HUB - Speed Control Center
15x RATE LIMITS for 100k emails in 10 minutes
"""
import redis
import time

redis_client = redis.Redis(host='localhost', port=6379, password='SendBabaRedis2024!', decode_responses=True)

HUB_CONFIG_KEY = 'sendbaba:hub:config'
HUB_RATE_LIMITS_KEY = 'sendbaba:hub:rate_limits'
HUB_WORKER_CONFIG_KEY = 'sendbaba:hub:worker_config'

BASE_LIMITS = {
    'gmail.com': 200, 'googlemail.com': 200,
    'yahoo.com': 150, 'yahoo.co.uk': 150, 'yahoo.co.in': 150,
    'hotmail.com': 150, 'outlook.com': 150, 'live.com': 150, 'msn.com': 150,
    'aol.com': 100, 'icloud.com': 100, 'me.com': 100,
    'default': 300
}

PROFILES = {
    'conservative': ('🐢 Conservative', 0.25, 7, '4 hours'),
    'balanced': ('⚖️ Balanced', 1, 28, '1 hour'),
    'aggressive': ('🔥 Aggressive', 4, 85, '20 min'),
    'turbo': ('🚀 TURBO (15x)', 15, 167, '10 min'),
    'ultra': ('⚡ ULTRA (20x)', 20, 240, '7 min'),
    'insane': ('💀 INSANE (30x)', 30, 350, '5 min'),
}

def calc_limits(mult):
    return {d: int(v * mult) for d, v in BASE_LIMITS.items()}

class EmailHub:
    def __init__(self):
        self.r = redis_client
    
    def set_profile(self, name):
        if name not in PROFILES:
            return {'error': f'Unknown: {name}'}
        n, mult, eps, t = PROFILES[name]
        limits = calc_limits(mult)
        self.r.hset(HUB_CONFIG_KEY, mapping={'profile': name, 'name': n, 'mult': str(mult), 'eps': str(eps), 'time': t})
        self.r.delete(HUB_RATE_LIMITS_KEY)
        self.r.hset(HUB_RATE_LIMITS_KEY, mapping={k: str(v) for k, v in limits.items()})
        return {'ok': True, 'profile': name, 'eps': eps}
    
    def get_profile(self):
        c = self.r.hgetall(HUB_CONFIG_KEY)
        l = self.r.hgetall(HUB_RATE_LIMITS_KEY)
        return {
            'profile': c.get('profile', 'turbo'),
            'name': c.get('name', '🚀 TURBO'),
            'mult': float(c.get('mult', 15)),
            'eps': int(c.get('eps', 167)),
            'limits': {k: int(v) for k, v in l.items()} if l else calc_limits(15)
        }
    
    def set_limit(self, domain, limit):
        self.r.hset(HUB_RATE_LIMITS_KEY, domain, str(limit))
    
    def set_multiplier(self, mult):
        limits = calc_limits(mult)
        self.r.delete(HUB_RATE_LIMITS_KEY)
        self.r.hset(HUB_RATE_LIMITS_KEY, mapping={k: str(v) for k, v in limits.items()})
        self.r.hset(HUB_CONFIG_KEY, mapping={'profile': 'custom', 'name': f'Custom {mult}x', 'mult': str(mult), 'eps': str(int(28*mult))})
    
    def set_workers(self, threads=150, chunk=2500):
        self.r.hset(HUB_WORKER_CONFIG_KEY, mapping={'threads': str(threads), 'chunk': str(chunk)})
    
    def get_workers(self):
        c = self.r.hgetall(HUB_WORKER_CONFIG_KEY)
        return {'threads': int(c.get('threads', 150)), 'chunk': int(c.get('chunk', 2500))}
    
    def get_stats(self):
        minute = int(time.time()) // 60
        keys = self.r.keys(f"rate:*:{minute}")
        total = sum(int(self.r.get(k) or 0) for k in keys)
        return {'total': total, 'eps': round(total / max(1, time.time() % 60), 1)}

def get_limit(domain):
    limit = redis_client.hget(HUB_RATE_LIMITS_KEY, domain)
    if limit: return int(limit)
    default = redis_client.hget(HUB_RATE_LIMITS_KEY, 'default')
    return int(default) if default else 4500

def check_rate(domain, org_id):
    minute = int(time.time()) // 60
    key = f"rate:{org_id}:{domain}:{minute}"
    count = redis_client.incr(key)
    redis_client.expire(key, 120)
    return count <= get_limit(domain)

def get_worker_config():
    c = redis_client.hgetall(HUB_WORKER_CONFIG_KEY)
    return {'threads': int(c.get('threads', 150)), 'chunk': int(c.get('chunk', 2500))}

def init_turbo():
    hub = EmailHub()
    hub.set_profile('turbo')
    hub.set_workers(150, 2500)
    print("🚀 Hub initialized: TURBO (15x) - 167 eps - 100k in 10 min")

if __name__ == '__main__':
    import sys
    hub = EmailHub()
    if len(sys.argv) < 2:
        p = hub.get_profile()
        s = hub.get_stats()
        print(f"\n📧 SendBaba Hub: {p['name']}")
        print(f"   Multiplier: {p['mult']}x | Target: {p['eps']} eps")
        print(f"   Current: {s['eps']} eps | This min: {s['total']}")
        print(f"\n   Commands: turbo | ultra | insane | status")
    elif sys.argv[1] == 'turbo':
        hub.set_profile('turbo')
        print("🚀 TURBO: 167 eps - 100k in 10 min")
    elif sys.argv[1] == 'ultra':
        hub.set_profile('ultra')
        print("⚡ ULTRA: 240 eps - 100k in 7 min")
    elif sys.argv[1] == 'insane':
        hub.set_profile('insane')
        print("💀 INSANE: 350 eps - 100k in 5 min")
    elif sys.argv[1] == 'status':
        s = hub.get_stats()
        print(f"📊 Current: {s['eps']} eps | This min: {s['total']}")
