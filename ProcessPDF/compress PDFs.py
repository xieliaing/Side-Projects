import os
import subprocess
import PyPDF2

"""
Step 1: Verify Ghostscript Installation
    Check if Ghostscript is Installed:

        Open a command prompt and type gs or gswin64c (depending on your system) to see if Ghostscript is installed and accessible.
        Install Ghostscript:

        If Ghostscript is not installed, you need to install it:
        Windows: Download and install from the official Ghostscript website.
        macOS: Install using Homebrew: brew install ghostscript.
        Linux: Install using your package manager, e.g., sudo apt-get install ghostscript.
    Add Ghostscript to PATH:

        Ensure that the directory containing the Ghostscript executable is in your system's PATH environment variable.
        For Windows, the executable is typically located in a directory like C:\Program Files\gs\gs9.xx\bin. You may need to add this directory to your PATH:
        Right-click on This PC or My Computer, and choose Properties.
        Click on Advanced system settings.
        Click on Environment Variables.
        Find the Path variable in the System variables section, select it, and click Edit.
        Click New, and paste the path to the Ghostscript bin directory.
        Click OK to close all dialogs.
"""

def compress_pdf(input_pdf_path, output_pdf_path, compression_level='ebook', gs_executable='gswin64c'):
    """
    Compress a PDF file using Ghostscript.

    :param input_pdf_path: Path to the input PDF file.
    :param output_pdf_path: Path to the output compressed PDF file.
    :param compression_level: Compression level: 'screen', 'ebook', 'printer', 'prepress'.
    :param gs_executable: The Ghostscript executable name or full path.
    """
    # Ghostscript command and options
    gs_command = [
        gs_executable,
        "-sDEVICE=pdfwrite",
        f"-dPDFSETTINGS=/{compression_level}",
        "-dNOPAUSE",
        "-dBATCH",
        "-dQUIET",
        f"-sOutputFile={output_pdf_path}",
        input_pdf_path
    ]

    # Execute the Ghostscript command
    subprocess.run(gs_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    print(f"PDF compressed successfully and saved as {output_pdf_path}")

# Paths to the input and output PDF files
input_pdf = "Passport 2 Full.pdf"
output_pdf = "Passport 2 Full_compressed.pdf"

# Compress the PDF
compress_pdf(input_pdf, output_pdf)
