"""python -m knos.zk verify DIR       check vk.json + proof.json + public.json in DIR off chain (pure Python)
python -m knos.zk ix DIR PROGRAM     print the knos_zk Verify instruction data (hex) and the verdict address

Exit status 0 when the proof verifies, 1 when it does not, 2 on a usage error."""

from __future__ import annotations

import sys

from solders.pubkey import Pubkey

from . import client, groth16


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "verify":
        vk, proof, inputs = groth16.load_dir(args[1])
        ok = groth16.verify(vk, proof, inputs)
        print("verified" if ok else "REFUSED: the proof does not verify for these public inputs")
        return 0 if ok else 1
    if len(args) == 3 and args[0] == "ix":
        _, proof, inputs = groth16.load_dir(args[1])
        program = Pubkey.from_string(args[2])
        print(bytes(client.verify_ix(program, proof, inputs).data).hex())
        print(client.verdict_address(program, inputs)[0])
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
