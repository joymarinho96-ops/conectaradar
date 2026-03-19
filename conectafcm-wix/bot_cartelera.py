import os
import json
from datetime import datetime
import requests
from bs4 import BeautifulSoup


URL_CARTELERA = "https://cartelera.med.unlp.edu.ar/"
URL_HISTOLOGIA = "https://sites.google.com/view/catedrahistologia"
NOMBRE_ARCHIVO_JSON = "noticias.json"
TIMEOUT_SEGUNDOS = 15
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 BotCartelera/1.0"
    )
}


def ruta_json_local():
    # Guarda noticias.json en la misma carpeta donde vive este script.
    carpeta_script = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(carpeta_script, NOMBRE_ARCHIVO_JSON)


def obtener_origen(base_url):
    # Devuelve esquema + dominio (por ejemplo: https://sitio.com).
    partes = base_url.split("/")
    if len(partes) >= 3:
        return partes[0] + "//" + partes[2]
    return base_url


def normalizar_url(base_url, href):
    # Convierte enlaces relativos en absolutos usando una URL base.
    if not href:
        return ""

    href = href.strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return obtener_origen(base_url).rstrip("/") + href
    return base_url.rstrip("/") + "/" + href.lstrip("/")


def es_enlace_util(url):
    # Filtra enlaces que no sirven para scraping de contenido.
    if not url:
        return False

    prefijos_descartados = ("#", "mailto:", "javascript:", "tel:")
    return not url.startswith(prefijos_descartados)


def slug_simple(texto):
    # Genera un slug simple para construir anclas estables.
    limpio = []
    for caracter in texto.lower():
        if caracter.isalnum():
            limpio.append(caracter)
        elif caracter.isspace():
            limpio.append("-")

    slug = "".join(limpio).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug


def descargar_html(url):
    # Descarga una pagina con timeout y user-agent.
    respuesta = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT_SEGUNDOS,
    )
    respuesta.raise_for_status()
    return respuesta.text


def agregar_item(noticias, urls_vistas, titulo, url, source, career, subject):
    # Agrega un item con metadatos si no esta duplicado por URL.
    if not titulo or not url or url in urls_vistas:
        return

    urls_vistas.add(url)
    noticias.append(
        {
            "titulo": titulo,
            "url": url,
            "source": source,
            "career": career,
            "subject": subject,
        }
    )


def extraer_cartelera_fcm():
    # Extrae noticias desde la cartelera general de FCM.
    html = descargar_html(URL_CARTELERA)
    soup = BeautifulSoup(html, "html.parser")
    noticias = []
    urls_vistas = set()

    selectores = [
        "article h1 a",
        "article h2 a",
        "article h3 a",
        ".entry-title a",
        ".post-title a",
        ".jeg_post_title a",
        "h2 a",
        "h3 a",
    ]

    for selector in selectores:
        for enlace in soup.select(selector):
            titulo = enlace.get_text(" ", strip=True)
            url = normalizar_url(URL_CARTELERA, enlace.get("href", ""))
            if not es_enlace_util(url):
                continue
            agregar_item(
                noticias=noticias,
                urls_vistas=urls_vistas,
                titulo=titulo,
                url=url,
                source="cartelera_fcm",
                career="",
                subject="",
            )

    # Fallback por si cambia el HTML del sitio.
    if not noticias:
        for enlace in soup.select("a[href]"):
            titulo = enlace.get_text(" ", strip=True)
            url = normalizar_url(URL_CARTELERA, enlace.get("href", ""))
            if not es_enlace_util(url):
                continue
            agregar_item(
                noticias=noticias,
                urls_vistas=urls_vistas,
                titulo=titulo,
                url=url,
                source="cartelera_fcm",
                career="",
                subject="",
            )

    return noticias


def extraer_histologia():
    # Extrae contenido util del sitio de Histologia.
    html = descargar_html(URL_HISTOLOGIA)
    soup = BeautifulSoup(html, "html.parser")
    noticias = []
    urls_vistas = set()

    selectores = [
        "main a[href]",
        "article a[href]",
        ".XqQF9c a[href]",
        "a[href]",
    ]

    for selector in selectores:
        for enlace in soup.select(selector):
            titulo = enlace.get_text(" ", strip=True)
            url = normalizar_url(URL_HISTOLOGIA, enlace.get("href", ""))
            if not es_enlace_util(url):
                continue
            agregar_item(
                noticias=noticias,
                urls_vistas=urls_vistas,
                titulo=titulo,
                url=url,
                source="histologia_site",
                career="Medicina",
                subject="Histolog\u00eda y Embriolog\u00eda",
            )

    # Fallback para textos visibles importantes (titulos o avisos).
    if not noticias:
        selectores_texto = [
            "main h1",
            "main h2",
            "main h3",
            "main [role='heading']",
            "h1",
            "h2",
            "h3",
        ]
        for selector in selectores_texto:
            for bloque in soup.select(selector):
                titulo = bloque.get_text(" ", strip=True)
                if len(titulo) < 6:
                    continue

                ancla = slug_simple(titulo)
                url = URL_HISTOLOGIA if not ancla else f"{URL_HISTOLOGIA}#{ancla}"
                agregar_item(
                    noticias=noticias,
                    urls_vistas=urls_vistas,
                    titulo=titulo,
                    url=url,
                    source="histologia_site",
                    career="Medicina",
                    subject="Histolog\u00eda y Embriolog\u00eda",
                )

    return noticias


def deduplicar_por_url(items):
    # Elimina duplicados entre fuentes manteniendo el primer item encontrado.
    resultado = []
    urls_vistas = set()

    for item in items:
        url = str(item.get("url", "")).strip()
        if not url or url in urls_vistas:
            continue
        urls_vistas.add(url)
        resultado.append(item)

    return resultado


def cargar_noticias_previas(ruta_json):
    # Si el archivo no existe, lo crea vacio para evitar errores.
    if not os.path.exists(ruta_json):
        with open(ruta_json, "w", encoding="utf-8") as archivo:
            json.dump([], archivo, ensure_ascii=False, indent=2)
        return []

    try:
        with open(ruta_json, "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(datos, list):
        return []

    noticias_validas = []
    for item in datos:
        if not isinstance(item, dict):
            continue

        titulo = str(item.get("titulo", "")).strip()
        url = str(item.get("url", "")).strip()
        if not titulo or not url:
            continue

        noticias_validas.append(
            {
                "titulo": titulo,
                "url": url,
                "source": str(item.get("source", "")).strip(),
                "career": str(item.get("career", "")).strip(),
                "subject": str(item.get("subject", "")).strip(),
            }
        )

    return noticias_validas


def guardar_noticias(ruta_json, noticias):
    # Persiste la lista combinada actual en formato JSON legible.
    with open(ruta_json, "w", encoding="utf-8") as archivo:
        json.dump(noticias, archivo, ensure_ascii=False, indent=2)


def detectar_noticias_nuevas(noticias_previas, noticias_actuales):
    # Compara por URL para identificar items nuevos.
    urls_previas = {item["url"] for item in noticias_previas if item.get("url")}
    return [item for item in noticias_actuales if item.get("url") not in urls_previas]


def imprimir_resumen(
    noticias_previas,
    noticias_actuales,
    noticias_nuevas,
    cantidad_cartelera,
    cantidad_histologia,
):
    # Imprime resumen solicitado + listado de items nuevos.
    fecha_ejecucion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Ejecucion: {fecha_ejecucion}")
    print(f"Cantidad de noticias anteriores: {len(noticias_previas)}")
    print(f"Items desde cartelera FCM: {cantidad_cartelera}")
    print(f"Items desde sitio de Histologia: {cantidad_histologia}")
    print(f"Total combinado: {len(noticias_actuales)}")
    print(f"Cantidad de items nuevos: {len(noticias_nuevas)}")
    print()
    print("Listado de items nuevos:")

    if not noticias_nuevas:
        print("No se detectaron items nuevos.")
        return

    for indice, item in enumerate(noticias_nuevas, start=1):
        print(f"{indice}. [{item['source']}] {item['titulo']}")
        print(f"   {item['url']}")


def main():
    ruta_json = ruta_json_local()
    noticias_previas = cargar_noticias_previas(ruta_json)

    try:
        noticias_cartelera = extraer_cartelera_fcm()
    except requests.RequestException as error:
        print(f"Error al obtener cartelera FCM: {error}")
        noticias_cartelera = []

    try:
        noticias_histologia = extraer_histologia()
    except requests.RequestException as error:
        print(f"Error al obtener sitio de Histologia: {error}")
        noticias_histologia = []

    noticias_actuales = deduplicar_por_url(noticias_cartelera + noticias_histologia)
    noticias_nuevas = detectar_noticias_nuevas(noticias_previas, noticias_actuales)

    guardar_noticias(ruta_json, noticias_actuales)
    imprimir_resumen(
        noticias_previas=noticias_previas,
        noticias_actuales=noticias_actuales,
        noticias_nuevas=noticias_nuevas,
        cantidad_cartelera=len(noticias_cartelera),
        cantidad_histologia=len(noticias_histologia),
    )


if __name__ == "__main__":
    main()
