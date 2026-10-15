"""The same protocol with a bug (50 uL moved instead of 100): it runs fine, and the sealed test catches it."""


async def protocol(lh, plate, tips):
    await lh.pick_up_tips(tips["A1:H1"])
    for src, dst in ((1, 2), (2, 3), (3, 4)):
        await lh.aspirate(plate[f"A{src}:H{src}"], vols=[50] * 8)
        await lh.dispense(plate[f"A{dst}:H{dst}"], vols=[50] * 8)
    await lh.drop_tips(tips["A1:H1"])
