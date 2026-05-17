import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "myhome"))

from own_client import GatewayClient

async def debug_audio():
    print("Connecting to gateway for Audio (WHO=16) Diagnostics...")
    c = GatewayClient("192.168.1.40", password="12345")
    res = await c.connect()
    
    if res.get("status") == "connected":
        print("\nConnection established! Passive listening mode activated.")
        print("Please interact with your audio system (turn on a zone, change volume, or select a source via a wall switch or HA).")
        print("Waiting 20 minutes for organic WHO=16 traffic...\n")
        
        start_idx = len(c._message_log)
        
        # We'll poll every second and print new messages
        for i in range(1200):
            await asyncio.sleep(1)
            current_idx = len(c._message_log)
            if current_idx > start_idx:
                new_msgs = list(c._message_log)[start_idx:current_idx]
                for m in new_msgs:
                    # Filter for WHO=16 (Audio)
                    is_audio = False
                    parsed = m.get("parsed", {})
                    if parsed.get("who") == 16:
                        is_audio = True
                    elif parsed.get("type") in ("raw_string", "unparsed") and ("*16*" in m["raw"] or "*#16*" in m["raw"]):
                        is_audio = True
                        
                    if is_audio:
                        print(f"[{m['direction']}] {m['raw']} -> {parsed.get('type')}")
                        desc = parsed.get("human_readable")
                        if desc:
                            print(f"    Action: {desc}")
                start_idx = current_idx
        
        print("\nDebug session complete. Disconnecting...")
        await c.disconnect()
    else:
        print("Failed to connect:", res)

if __name__ == "__main__":
    asyncio.run(debug_audio())
