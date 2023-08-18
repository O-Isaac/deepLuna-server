from translation import TranslationUtils
from flask import Flask, send_file, request
from io import StringIO, BytesIO
from itertools import chain
from utils import create_logger

import pandas as pd
import pygsheets

app = Flask(__name__)
tl = TranslationUtils(database_path="assets/database.json")
gs = pygsheets.authorize(service_file="assets/certificate.json")


@app.route('/api/sheets/get/<scene_id>', methods=['GET'])
def get_scene(scene_id):
    """
    Export translations for a scene to a Google Sheet.

    Parameters:
        scene_id (int): The ID of the scene for which translations are to be exported.

    Returns:
        str: CSV-formatted text containing translations.

    Raises:
        Exception: If an error occurs during the export process, "Not Found" is returned with a 404 status code.

    Description:
        This function exports translations for a scene specified by its `scene_id` to a Google Sheet. It generates
        a CSV-formatted text containing translations using `tl.generate_csv_from_scene(scene_id)` and returns it.
    """
    try:
        buffer = StringIO()

        scene = tl.generate_csv_from_scene(scene_id)
        scene.to_csv(buffer, index=False, header=False)

        csv_text = buffer.getvalue()
        buffer.seek(0)

        return csv_text, 200, {'Content-Type': 'text/plain; charset=utf8'}
    except Exception as error:
        print(error)
        return "Not Found", 404
    
@app.route('/api/sheets/current/<scene_id>', methods=['GET'])
def export_scene(scene_id):
    """
    Export scene content with HTML line breaks for translation checks.

    Parameters:
        scene_id (int): The ID of the scene to be exported.

    Returns:
        str: Scene content with HTML line breaks.

    Raises:
        Exception: If an error occurs during the export process, "Not Found" is returned with a 404 status code.

    Description:
        This function exports the content of a scene specified by its scene_id, intended for translation checks before generating the "mrg" file.
    """
    try:
        return tl.export_current_tl_scene(scene_id), 200, {'Content-Type': 'text/plain; charset=utf8'}
    except Exception as error:
        print(error)
        return "Not Found", 404

@app.route('/api/database/save', methods=['GET'])
def save_database():
    """
    Save the current translation state in a database file.

    Returns:
        str: "Success" if the operation succeeds, "Internal Server Error" if there's an issue.

    Description:
        This function is used to save the current translation state into a database file. It calls
        `tl.generate_db_file()` to perform the saving operation. If the operation is successful,
        it returns "Success" with a status code 200. Otherwise, if an exception occurs during the process,
        it returns "Internal Server Error" with a status code 503.
    """
    try:
        tl.generate_db_file()
        return "Success", 200, {'Content-Type': 'text/plain; charset=utf8'}
    except Exception as error:
        return "Internal Server Error", 503

@app.route('/api/mrg/gen', methods=['GET'])
def generate_mrg():
    """
    Generate an 'mrg' file with translated lines.

    Returns:
        File: The generated 'mrg' file as an attachment.

    Raises:
        Exception: If an error occurs during the generation process, "Internal Server Error" is returned with a
                   status code 503.

    Description:
        This function generates an 'mrg' file with translated lines using `tl.generate_script_mrg()`. The generated
        content is written to a BytesIO buffer and returned as a downloadable attachment using Flask's `send_file`
        function. If any exceptions occur during the generation process, the function catches them and returns
        "Internal Server Error" with a status code 503.
    """
    try:
        buffer = BytesIO()
        file_name, file_data = tl.generate_script_mrg()

        buffer.write(file_data)
        buffer.seek(0)

        return send_file(buffer, download_name=file_name, as_attachment=True)
    except Exception as error:
        print(error)
        return "Internal Server Error", 503

@app.route('/api/sheet/pull', methods=['POST'])
def upload_csv():
    """
    Receive and apply translations from a CSV file to the corresponding scenes.

    Returns:
        str: "Success" if the translations are successfully applied, "Error" if there's an issue.

    Description:
        This function receives a CSV file containing translated lines from a request. It iterates through the
        uploaded files and processes each one using `tl.process_scene_csv(csv_file, fileName)`, which applies
        the translations to the corresponding scenes. If the operation is successful, it returns "Success" with
        a 200 status code. Otherwise, if an exception occurs during the process, it returns "Error" with a 500
        status code.
    """
    try:
        
        for fileName in request.files:
            csv_file = request.files[fileName]
            tl.process_scene_csv(csv_file, fileName)
        
        return "Success", 200, {'Content-Type': 'text/plain; charset=utf8'}
    except Exception as e:
        return "Error", 500

@app.route('/api/sheet/pull/<sheet_id>', methods=['GET'])
def pull_sheet(sheet_id):
    try:
        stream, logger = create_logger(sheet_id)
        spreadsheet = gs.open_by_key(sheet_id)
        indice = spreadsheet.worksheet_by_title('Indice')
        
        # Process ids
        cell_ids = indice.get_values(
            "A3", 
            "A", 
            include_tailing_empty_rows=False, 
            include_tailing_empty=False
        )

        # Delete first title
        del cell_ids[:2]

        # Get Each worksheet
        for cell_id in list(chain(*cell_ids)):
            scene_worksheet = spreadsheet.worksheet_by_title(cell_id)
            scene_csv = scene_worksheet.get_values("1", "1000", include_tailing_empty_rows=False, include_tailing_empty=False)

            df = pd.DataFrame(scene_csv)
            lines = df.to_csv(header=False, index=False)
            tl.process_scene_csv(StringIO(lines), cell_id, logger)

        return stream.getvalue(), 200, {'Content-Type': 'text/plain; charset=utf8'}
    except Exception as e:
        return "Error", 500

if __name__ == '__main__':
    app.run(debug=True)