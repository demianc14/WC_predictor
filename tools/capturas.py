"""Genera las capturas de la web para el README y para LinkedIn.

Abre `app/index.html` (la web real, con los datos que tenga en ese momento) en
Chrome headless, una vez por vista: a cada copia temporal se le agrega un script
que llama a `goto(...)`, la misma navegación de los botones, y apaga las
animaciones para que la foto no salga a mitad de una.

    pip install pillow
    python -m tools.capturas      # escribe docs/img/web*.png, web.gif y linkedin-*.png

Requiere Google Chrome instalado (la ruta de macOS es el default; `CHROME=...` la
cambia) y red para las fuentes de Google. No modifica `app/index.html`.
"""

from __future__ import annotations

import html
import os
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from PIL import Image

RAIZ = Path(__file__).resolve().parents[1]
WEB = RAIZ / "app" / "index.html"
SALIDA = RAIZ / "docs" / "img"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
URL = "demianc14.github.io/WC_predictor"

ESCRITORIO = (1280, 800)
CELULAR = (390, 844)
ESCALA = 2

# Vista → (argumento de goto(), elemento que debe quedar arriba). El orden es el del GIF.
# En las ligas lo propio de cada panel está debajo del encabezado común: se baja hasta ahí.
ESCENAS = {
    "inicio": ("home", None),
    "proxima": ("next", None),
    "tabla": ("pl:tabla", "#plTable"),
    "jornada": ("pl:jornada", "#plNext"),
    "mercado": ("pl:mercado", "#plBt"),
    "ranking": ("rank", None),
    "mundial": ("cup", None),
}
MOSAICO_CELULAR = ["inicio", "tabla", "jornada", "mercado"]

FONDO = "#060D0A"  # --paper de la web


def _escena(destino: str, arriba: str | None) -> str:
    # Baja hasta el elemento, dejando lugar para la barra fija y el título del bloque.
    bajar = (
        f"const el=document.querySelector({arriba!r});"
        "const barra=document.querySelector('.topbar').getBoundingClientRect().bottom;"
        "window.scrollTo(0,el.getBoundingClientRect().top+window.scrollY-barra-90);"
        if arriba
        else "window.scrollTo(0,0);"
    )
    return f"""<style>*,*::before,*::after{{animation:none!important;transition:none!important}}
html{{scroll-behavior:auto!important}}</style>
<script>window.addEventListener("load",()=>{{goto({destino!r});{bajar}}});</script>
</body>"""


def _chrome(url: str, ancho: int, alto: int, salida: Path) -> None:
    subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--hide-scrollbars",
            "--allow-file-access-from-files",
            f"--window-size={ancho},{alto}",
            f"--force-device-scale-factor={ESCALA}",
            "--virtual-time-budget=6000",
            f"--screenshot={salida}",
            url,
        ],
        check=True,
        capture_output=True,
    )


def _en_marco(pagina: Path, ancho: int, alto: int, png: Path) -> Image.Image:
    """Fotografía la página dentro de un iframe de ancho × alto y la recorta.

    Chrome headless no achica la ventana a menos de ~500 px y, si la página misma
    se desplaza, la captura sale corrida. Dentro de un iframe las dos cosas andan.
    """
    marco = pagina.with_name(f"{png.stem}-marco.html")
    marco.write_text(
        f'<body style="margin:0;background:{FONDO}"><iframe src="{pagina.name}" '
        f'style="border:0;width:{ancho}px;height:{alto}px"></iframe></body>',
        "utf-8",
    )
    _chrome(marco.as_uri(), max(ancho, 500) + 100, alto, png)
    return Image.open(png).convert("RGB").crop((0, 0, ESCALA * ancho, ESCALA * alto))


def _capturar(tmp: Path) -> tuple[dict[str, Image.Image], dict[str, Image.Image]]:
    fuente = WEB.read_text("utf-8")
    assert fuente.count("</body>") == 1, "app/index.html cambió de forma: revisar _escena"
    escritorio: dict[str, Image.Image] = {}
    celular: dict[str, Image.Image] = {}
    for nombre, (destino, arriba) in ESCENAS.items():
        pagina = tmp / f"{nombre}.html"
        pagina.write_text(fuente.replace("</body>", _escena(destino, arriba)), "utf-8")
        escritorio[nombre] = _en_marco(pagina, *ESCRITORIO, tmp / f"{nombre}-escritorio.png")
        if nombre in MOSAICO_CELULAR:
            celular[nombre] = _en_marco(pagina, *CELULAR, tmp / f"{nombre}-celular.png")
    return escritorio, celular


def _mosaico(cuadros: list[Image.Image], margen: int = 24) -> Image.Image:
    w, h = cuadros[0].size
    lienzo = Image.new("RGB", (len(cuadros) * (w + margen) + margen, h + 2 * margen), "#1B2A22")
    for i, c in enumerate(cuadros):
        lienzo.paste(c, (margen + i * (w + margen), margen))
    return lienzo


# Portadas: HTML con los tokens y fuentes de la web, fotografiado al tamaño exacto.
# El texto repite solo lo que ya dice el README; ninguna cifra nueva.
PORTADA_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@800;900&family=Hanken+Grotesk:wght@400;500;600&family=Martian+Mono:wght@400;500&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
body{width:__W__px;height:__H__px;overflow:hidden;background:#060D0A;color:#EAF3E4;
  font-family:'Hanken Grotesk',sans-serif;position:relative}
.k{font:500 15px 'Martian Mono',monospace;letter-spacing:.08em;text-transform:uppercase;
  color:#D6FF3D}
h1{font-family:'Big Shoulders Display',sans-serif;font-weight:900;line-height:.95;
  letter-spacing:-.01em;margin-top:18px}
h1 em{font-style:normal;color:#D6FF3D}
ul{list-style:none;margin-top:26px;display:grid;gap:12px;font-size:20px;color:#C9D7C3}
li::before{content:"";display:inline-block;width:9px;height:9px;border-radius:50%;
  background:#D6FF3D;margin-right:12px;vertical-align:2px}
.url{position:absolute;font:500 16px 'Martian Mono',monospace;color:#8CA194}
img{display:block;border-radius:14px;border:1px solid rgba(190,255,215,.20);
  box-shadow:0 30px 80px rgba(0,0,0,.6)}
"""

PORTADA_TEXTO = {
    "kicker": "Predictor de fútbol · open source",
    "titulo": "Predicciones publicadas <em>antes</em> del partido, medidas después.",
    "puntos": [
        "Cinco grandes ligas y selecciones 2026-27",
        "Dixon-Coles y un modelo supervisado, walk-forward",
        "Comparado de forma honesta contra el mercado",
        "Ciclo diario automático con GitHub Actions",
    ],
}


def _portada(ancho: int, alto: int, cuerpo: str, tmp: Path, nombre: str) -> Image.Image:
    css = PORTADA_CSS.replace("__W__", str(ancho)).replace("__H__", str(alto))
    pagina = tmp / f"{nombre}.html"
    pagina.write_text(f"<!doctype html><meta charset='utf-8'><style>{css}</style>{cuerpo}", "utf-8")
    png = tmp / f"{nombre}.png"
    _chrome(pagina.as_uri(), ancho, alto, png)
    return Image.open(png).convert("RGB").resize((ancho, alto), Image.Resampling.LANCZOS)


def _portadas(tmp: Path) -> tuple[Image.Image, Image.Image]:
    t = PORTADA_TEXTO
    puntos = "".join(f"<li>{html.escape(p)}</li>" for p in t["puntos"])
    texto = f'<div class="k">{t["kicker"]}</div><h1>{t["titulo"]}</h1><ul>{puntos}</ul>'
    url = f'<div class="url" style="left:64px;bottom:44px">{URL}</div>'

    horizontal = _portada(
        1200,
        627,
        f'<div style="position:absolute;left:64px;top:64px;width:500px">'
        f'{texto.replace("<h1>", "<h1 style=font-size:62px>")}</div>{url}'
        f'<img src="tabla-escritorio.png" style="position:absolute;left:610px;top:70px;'
        f'width:820px">',
        tmp,
        "linkedin-1200x627",
    )
    vertical = _portada(
        1080,
        1350,
        f'<div style="position:absolute;left:64px;top:72px;right:64px">'
        f'{texto.replace("<h1>", "<h1 style=font-size:84px>")}</div>{url}'
        f'<img src="inicio-celular-recorte.png" style="position:absolute;left:64px;top:600px;'
        f'width:300px">'
        f'<img src="tabla-celular-recorte.png" style="position:absolute;left:390px;top:600px;'
        f'width:300px">'
        f'<img src="jornada-celular-recorte.png" style="position:absolute;left:716px;top:600px;'
        f'width:300px">',
        tmp,
        "linkedin-1080x1350",
    )
    return horizontal, vertical


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        escritorio, celular = _capturar(tmp)
        for nombre, img in celular.items():  # las portadas las cargan por archivo
            img.save(tmp / f"{nombre}-celular-recorte.png")
        horizontal, vertical = _portadas(tmp)

    escritorio["inicio"].save(SALIDA / "web.png", optimize=True)
    _mosaico([celular[n] for n in MOSAICO_CELULAR]).save(SALIDA / "web-movil.png", optimize=True)
    horizontal.save(SALIDA / "linkedin-1200x627.png", optimize=True)
    vertical.save(SALIDA / "linkedin-1080x1350.png", optimize=True)

    cuadros = [
        img.resize((960, 600), Image.Resampling.LANCZOS) for img in escritorio.values()
    ]
    cuadros[0].save(
        SALIDA / "web.gif",
        save_all=True,
        append_images=cuadros[1:],
        duration=2200,
        loop=0,
        optimize=True,
    )
    print(f"Listo ({date.today().isoformat()}): {SALIDA}")
    for f in sorted(SALIDA.iterdir()):
        print(f"  {f.name}  {f.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
