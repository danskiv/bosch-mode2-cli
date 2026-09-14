import asyncio
import pytest
from bosch_mode2_cli.client import BoschSol2000Client
from bosch_mode2_cli.simulator import BoschSol2000Simulator


@pytest.mark.asyncio
async def test_client_connect_and_snapshot():
    port = 17702
    pin = "1234"
    sim = BoschSol2000Simulator(host="127.0.0.1", port=port, user_pin=pin)
    await sim.start()

    client = BoschSol2000Client(host="127.0.0.1", port=port, user_pin=pin)

    try:
        await client.connect(load_history=True)
        assert client.is_connected is True

        snapshot = client.get_snapshot()
        assert snapshot.model_name == "Solution 2000"
        assert len(snapshot.points) == 8
        assert snapshot.points[1].name == "Front Door"
        assert len(snapshot.areas) == 1
        assert snapshot.areas[1].name == "Area 1"

        # Check transactions loaded from history
        assert len(client.transactions) > 0

    finally:
        await client.disconnect()
        await sim.stop()
