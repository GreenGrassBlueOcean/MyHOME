import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "myhome"))

from own_client import GatewayClient

async def test():
    print("Testing MCP GatewayClient...")
    c = GatewayClient("192.168.1.40", password="12345")
    
    print("Connecting...")
    res = await c.connect()
    print("Connect result:")
    print(json.dumps(res, indent=2))
    
    if res.get("status") == "connected":
        print("\nSending WHO=16 (Audio) status request for Zone 11...")
        start_idx = len(c._message_log)
        sres = await c.send_raw("*#16*11##")
        print("Send raw returned:", sres)
        
        print("\nWaiting 5 seconds for responses...")
        await asyncio.sleep(5)
        
        responses = list(c._message_log)[start_idx:]
        print("\nBus responses:")
        for m in responses:
            print(f"[{m['direction']}] {m['raw']} -> {m.get('parsed', {}).get('type')}")
            if "human_readable" in m.get("parsed", {}):
                print(f"    Desc: {m['parsed']['human_readable']}")
        
        print("\nDisconnecting...")
        await c.disconnect()
        print("Disconnected.")

if __name__ == "__main__":
    asyncio.run(test())
