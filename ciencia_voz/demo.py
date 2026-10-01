import pymupdf


def demo_pdf() -> bytes:
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((50, 65), "1 Introducao", fontsize=20, fontname="hebo")
    page.insert_textbox((50, 95, 540, 150),
                        "Este documento demonstra a selecao de secoes cientificas. "
                        "A energia de repouso depende da massa e da velocidade da luz.", fontsize=11)
    page.insert_text((50, 200), "1.1 Relacao entre massa e energia", fontsize=15, fontname="hebo")
    page.insert_text((50, 235), "E = m c^2", fontsize=12)
    page.insert_textbox((50, 265, 540, 340),
                        "E representa energia, m representa massa e c e a velocidade da luz no vacuo. "
                        "A formula precisa de preparacao cientifica para narrar o expoente corretamente.", fontsize=11)
    page = pdf.new_page()
    page.insert_text((50, 65), "2 Metodos", fontsize=20, fontname="hebo")
    page.insert_textbox((50, 100, 540, 170),
                        "Foram comparadas medidas de massa em quilogramas e energia em joules. "
                        "As unidades devem ser preservadas durante a narracao.", fontsize=11)
    page.insert_text((50, 215), "2.1 Procedimento experimental", fontsize=15, fontname="hebo")
    page.insert_textbox((50, 250, 540, 325),
                        "Calibrar o instrumento antes de registrar as observacoes. "
                        "Repetir as medicoes e registrar a incerteza experimental.", fontsize=11)
    pdf.set_toc([[1, "1 Introducao", 1], [2, "1.1 Relacao entre massa e energia", 1],
                 [1, "2 Metodos", 2], [2, "2.1 Procedimento experimental", 2]])
    data = pdf.tobytes()
    pdf.close()
    return data
