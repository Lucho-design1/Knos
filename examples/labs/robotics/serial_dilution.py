"""A researcher's submitted protocol (example): a 1:2 serial dilution across columns 1 to 4 of a 96-well plate, eight
channels at once. Knos runs it on PyLabRobot's simulator against the sealed test before any robot lab is paid."""


async def protocol(lh, plate, tips):
    await lh.pick_up_tips(tips["A1:H1"])
    for src, dst in ((1, 2), (2, 3), (3, 4)):
        await lh.aspirate(plate[f"A{src}:H{src}"], vols=[100] * 8)
        await lh.dispense(plate[f"A{dst}:H{dst}"], vols=[100] * 8)
    await lh.drop_tips(tips["A1:H1"])
