import socket
import time
import sys
import os

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_connection(host, port):
    print(f"Testing connection to {host}:{port}...", end=" ")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((host, int(port)))
        s.close()
        print("✅ SUCCESS")
        return True
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False

def main():
    test_pools = [
        ("public-pool.io", 21496),
        ("stratum.ckpool.org", 3333),
        ("btc.f2pool.com", 3333)
    ]
    print("--- NETWORK DIAGNOSTIC START ---")
    all_failed = True
    for host, port in test_pools:
        if test_connection(host, port):
            all_failed = False
    
    print("\nTesting Binance API connectivity...", end=" ")
    try:
        import requests
        r = requests.get("https://api.binance.com/api/v3/ping", timeout=5)
        if r.status_code == 200:
            print("✅ SUCCESS")
        else:
            print(f"❌ FAILED (Status: {r.status_code})")
    except Exception as e:
        print(f"❌ FAILED: {e}")
    
    if all_failed:
        print("\n🚨 CRITICAL DIAGNOSIS: Your Firewall is blocking ALL mining traffic.")
    else:
        print("\n🟢 Network is OK. The problem is likely the Wallet Address or Pool Difficulty.")

if __name__ == "__main__":
    main()
