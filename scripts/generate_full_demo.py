from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / 'data' / 'demo' / 'synthetic_100k_23andme_like_GRCh38.txt'
variants = [
    ('rs6025', '1', 169549811, 'CT'),
    ('rs12777823', '1', 11601420, 'AG'),
    ('rs28371704', '2', 121000845, 'AG'),
    ('rs429358', '19', 44908684, 'TC'),
    ('rs1111111', '4', 200000000, 'GG'),
    ('rs2222222', '5', 300000000, 'TC'),
    ('rs999000001', '19', 11102786, 'AG'),
]

lines = []
for i in range(100_000):
    rsid, chrom, pos, geno = variants[i % len(variants)]
    if i % 7 == 0:
        rsid = f'rs{i:06d}'
        chrom = str((i % 22) + 1)
        pos = 1_000_000 + i
        geno = 'CT' if i % 2 == 0 else 'TT'
    lines.append(f'{rsid} {chrom} {pos} {geno}')

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f'Wrote {len(lines)} lines to {out}')
