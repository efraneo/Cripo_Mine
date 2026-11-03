import socket
import time
from config import load_secrets

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
    cfg = load_secrets()
    pool_url = cfg.get("POOL_URL", "")
    
    if not pool_url:
        print("ERROR: No POOL_URL found in secrets.")
        return

    # Parse stratum+tcp://host:port
    try:
        clean_url = pool_url.replace("stratum+tcp://", "").replace("stratum+ssl://", "").replace("ssl://", "")
        if "/" in clean_url:
            clean_url = clean_url.split("/")[0]
        
        host, port = clean_url.split(":")
        
        # Test pool connection
        connected = test_connection(host, port)
        
        # Test Binance API connectivity
        print("Testing Binance API connectivity...", end=" ")
        try:
            import requests
            r = requests.get("https://api.binance.com/api/v3/ping", timeout=5)
            if r.status_code == 200:
                print("✅ SUCCESS")
            else:
                print(f"❌ FAILED (Status: {r.status_code})")
        except Exception as e:
            print(f"❌ FAILED: {e}")
            
        if not connected:
            print("\n🚨 DIAGNOSIS: Your Firewall is blocking the miner's connection to the pool.")
            print("ACTION: Add xmrig.exe to Windows Firewall Allow-list (Inbound/Outbound).")
        else:
            print("\n🟢 Network is OK. The problem is likely the Wallet Address or Pool Difficulty.")

    except Exception as e:
        print(f"ERROR during test: {e}")

if __name__ == "__main__":
    main()
