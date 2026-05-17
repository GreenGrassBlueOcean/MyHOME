import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "myhome"))

from own_client import GatewayClient
from ownd.message import OWNSoundEvent

async def active_discovery():
    print("Connecting to gateway for Active Audio Discovery...")
    c = GatewayClient("192.168.1.40", password="12345")
    res = await c.connect()
    
    if res.get("status") == "connected":
        print("Connected! Using the 'Event Session Hack' to safely map the matrix...")
        
        # We will test areas 0, 1, 2, 3 and points 1-8
        # Addresses: 01-08, 11-18, 21-28, 31-38
        addresses = []
        for area in ["0", "1", "2", "3"]:
            for point in range(1, 9):
                addresses.append(f"{area if area != '0' else ''}{point}")
                
        # Send status request for each address over the EVENT session
        start_idx = len(c._message_log)
        found_zones = set()
        
        for addr in addresses:
            frame = f"*#16*{addr}##"
            # Send directly over event session to avoid Command Session NACK drops
            c._event_session._stream_writer.write(frame.encode())
            await c._event_session._stream_writer.drain()
            await asyncio.sleep(0.2) # 200ms delay to protect the gateway serial bridge
            
        print("Scan complete. Waiting 2 seconds for all responses to arrive...\n")
        await asyncio.sleep(2)
        
        print("=== DISCOVERED AUDIO ZONES ===")
        responses = list(c._message_log)[start_idx:]
        
        for m in responses:
            if m['direction'] == "RX":
                parsed = m.get("parsed", {})
                if parsed.get("who") == 16:
                    where = parsed.get("where")
                    if where and where not in found_zones:
                        found_zones.add(where)
                        state = "ON" if "is_on" in m["raw"] or "*16*1*" in m["raw"] else "OFF"
                        if "*16*0*" in m["raw"]: state = "OFF"
                        print(f"✅ Found Audio Zone: {where} (Last reported state: {state})")
                        print(f"   Raw Response: {m['raw']}")
        
        if not found_zones:
            print("No audio zones responded. (They might be in deep sleep or addressed differently)")
            
        await c.disconnect()
    else:
        print("Failed to connect:", res)

if __name__ == "__main__":
    asyncio.run(active_discovery())
