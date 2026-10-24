"""Validacion estructural de PDF sin dependencias externas (reportlab genera, aqui solo se lee)."""
import base64
import re
import zlib


def streams(datos: bytes) -> list[bytes]:
    """Decodifica los streams con /Filter (ASCII85 y/o Flate); falla si alguno esta corrupto."""
    out = []
    patron = re.compile(rb"<<((?:(?!>>).)*?/Filter\s*\[([^\]]*)\](?:(?!>>).)*?)>>\s*stream\r?\n", re.S)
    for m in patron.finditer(datos):
        largo = int(re.search(rb"/Length\s+(\d+)", m.group(1)).group(1))
        crudo = datos[m.end():m.end() + largo]
        for filtro in re.findall(rb"/(\w+)", m.group(2)):
            if filtro == b"ASCII85Decode":
                limpio = crudo.strip()
                crudo = base64.a85decode(limpio[:-2] if limpio.endswith(b"~>") else limpio)
            elif filtro == b"FlateDecode":
                crudo = zlib.decompress(crudo)
        out.append(crudo)
    return out


def texto_pdf(datos: bytes) -> str:
    """Textos dibujados con (..) Tj en los streams de contenido."""
    return " ".join(t.decode("latin-1") for s in streams(datos) for t in re.findall(rb"\((.*?)\) Tj", s))


def validar_pdf(datos: bytes) -> dict:
    """Cabecera, %%EOF, startxref -> tabla xref, cada objeto 'n' en su offset, catalogo, paginas y
    todos los streams decodificables."""
    assert datos.startswith(b"%PDF-1."), datos[:10]
    assert datos.rstrip().endswith(b"%%EOF")
    m = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", datos.rstrip() + b"\n")
    assert m, "sin startxref"
    pos = int(m.group(1))
    assert datos[pos:pos + 4] == b"xref", "startxref no apunta a la tabla xref"
    tabla = re.match(rb"xref\s+0 (\d+)\s+((?:\d{10} \d{5} [nf]\s*)+)", datos[pos:])
    assert tabla, "tabla xref ilegible"
    n = int(tabla.group(1))
    entradas = re.findall(rb"(\d{10}) (\d{5}) ([nf])", tabla.group(2))
    assert len(entradas) == n
    for i, (off, _gen, tipo) in enumerate(entradas):
        if tipo == b"n":
            assert re.match(rb"%d 0 obj" % i, datos[int(off):int(off) + 20]), f"objeto {i} mal ubicado"
    paginas = len(re.findall(rb"/Type\s*/Page\b", datos))
    assert paginas >= 1 and re.search(rb"/Type\s*/Catalog", datos)
    decodificados = streams(datos)
    return {"objetos": n - 1, "paginas": paginas, "streams_decodificados": len(decodificados),
            "bytes": len(datos)}
