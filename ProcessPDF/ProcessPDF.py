#
# Generated by chatGPT, debugged by Liang Xie, 2023-04
#
import os
import streamlit as st
import PyPDF2

# Function to merge PDFs
def merge_pdfs(pdfs):
    merged_pdf = PyPDF2.PdfFileMerger()
    for pdf in pdfs:
        merged_pdf.add_pdf(pdf)
    output_path = 'merged.pdf'
    merged_pdf.write(output_path)
    merged_pdf.close()
    return output_path

# Function to merge PDFs
def combine_pdfs(pdfs, output_file='merged.pdf'):
    pdf_files = pdfs
    pdf_files.sort()
    pdf_writer = PyPDF2.PdfFileWriter()

    for pdf_file in pdf_files:
        pdf_reader = PyPDF2.PdfFileReader(open(pdf_file, 'rb'))
        for page in range(pdf_reader.getNumPages()):
            pdf_writer.addPage(pdf_reader.getPage(page))

    with open(output_file, 'wb') as output:
        pdf_writer.write(output)

# Function to extract pages from a PDF
def extract_pages(pdf_file, pages):
    extracted_pdf = PyPDF2.PdfReader(pdf_file)
    output_path = 'extracted.pdf'
    writer = PyPDF2.PdfWriter()
    for page in pages:
        writer.add_page(extracted_pdf.pages[page - 1])
    with open(output_path, 'wb') as f:
        writer.write(f)
    return output_path

# Function to compress a PDF
def compress_pdf(pdf_file):
    output_path = 'compressed.pdf'
    input_pdf = open(pdf_file, 'rb')
    pdf_reader = PyPDF2.PdfReader(input_pdf)
    pdf_writer = PyPDF2.PdfWriter()
    for page in pdf_reader.pages:
        pdf_writer.add_page(page)
    pdf_writer.compress = True
    with open(output_path, 'wb') as f:
        pdf_writer.write(f)
    return output_path

# Set up the Streamlit app
st.title('PDF Manipulation')

# Define the options for the menus
options = ['Merge PDFs', 'Extract Pages', 'Compress PDF']

# Create a sidebar with the menu options
selected_option = st.sidebar.selectbox('Select an option', options)

# Merge PDFs menu
if selected_option == 'Merge PDFs':
    st.header('Merge PDFs')
    pdf_files = st.file_uploader('Select PDF files to merge', accept_multiple_files=True, type=['pdf'])
    if st.button('Merge'):
        if pdf_files:
            pdf_filepaths = [os.path.join('', pdf_file.name) for pdf_file in pdf_files]
            merged_filepath = combine_pdfs(pdf_filepaths)
            st.success(f'PDFs merged successfully. Merged PDF saved to {merged_filepath}')

# Extract Pages menu
elif selected_option == 'Extract Pages':
    st.header('Extract Pages')
    pdf_file = st.file_uploader('Select a PDF file', type=['pdf'])
    pages = st.multiselect('Select pages to extract', options=list(range(1, 11)))
    if st.button('Extract'):
        if pdf_file and pages:
            pdf_filepath = os.path.join('', pdf_file.name)
            extracted_filepath = extract_pages(pdf_filepath, pages)
            st.success(f'Pages extracted successfully. Extracted PDF saved to {extracted_filepath}')

# Compress PDF menu
elif selected_option == 'Compress PDF':
    st.header('Compress PDF')
    pdf_file = st.file_uploader('Select a PDF file', type=['pdf'])
    if st.button('Compress'):
        if pdf_file:
            pdf_filepath = os.path.join('', pdf_file.name)
            compressed_filepath = compress_pdf(pdf_filepath)
            st.success(f'PDF compressed successfully. Compressed PDF saved to {compressed_filepath}')