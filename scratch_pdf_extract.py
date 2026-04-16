import fitz
doc = fitz.open(r'C:\Users\laurensvdb\Downloads\WHO_16.pdf')
with open('pdf_output.txt', 'w', encoding='utf-8') as f:
    for page in doc:
        f.write(page.get_text())
