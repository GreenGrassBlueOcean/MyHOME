import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "myhome"))

from own_client import GatewayClient

async def turn_off_bureau():
    print("Connecting to gateway...")
    c = GatewayClient("192.168.1.40", password="12345")
    res = await c.connect()
    
    if res.get("status") == "connected":
        lights_to_turn_off = ["79", "65", "64"]
        
        for address in lights_to_turn_off:
            frame = f"*1*1*{address}##"
            print(f"Turning ON light {address} with frame: {frame}")
            result = await c.send_raw(frame)
            print(f"Response: {result}")
            await asyncio.sleep(0.3)  # Small delay between commands
            
        await c.disconnect()
        print("Done.")
    else:
        print("Failed to connect:", res)

if __name__ == "__main__":
    asyncio.run(turn_off_bureau())
