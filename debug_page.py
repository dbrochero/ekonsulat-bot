from playwright.sync_api import sync_playwright

URL = "https://secure.e-konsulat.gov.pl/placowki/164/sprawy-paszportowe/wizyty/formularz"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    print("Navegando a la URL...")
    page.goto(URL, timeout=60000, wait_until="networkidle")
    page.wait_for_timeout(4000)
    
    
    # Guardamos el HTML para ver los nombres exactos de los campos
    with open("debug_page.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    print("HTML guardado en debug_page.html")
    
    # Listar todas las imágenes o campos de texto detectados en la página
    imgs = page.locator("img").all()
    print(f"\nSe encontraron {len(imgs)} imágenes en la página:")
    for idx, img in enumerate(imgs):
        src = img.get_attribute("src") or ""
        id_attr = img.get_attribute("id") or ""
        alt_attr = img.get_attribute("alt") or ""
        print(f" - Img {idx}: id='{id_attr}', src='{src[:60]}...', alt='{alt_attr}'")

    inputs = page.locator("input").all()
    print(f"\nSe encontraron {len(inputs)} campos input en la página:")
    for idx, inp in enumerate(inputs):
        name = inp.get_attribute("name") or ""
        id_attr = inp.get_attribute("id") or ""
        placeholder = inp.get_attribute("placeholder") or ""
        print(f" - Input {idx}: id='{id_attr}', name='{name}', placeholder='{placeholder}'")

    browser.close()
