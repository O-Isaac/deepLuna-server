from translation import TranslationUtils
from flask import Flask, send_file, request
from io import StringIO, BytesIO

app = Flask(__name__)
tl = TranslationUtils()

@app.route('/api/sheets/get/<scene_id>', methods=['GET'])
def get_scene(scene_id):
    try:
        buffer = StringIO()

        scene = tl.generate_csv_from_scene(scene_id)
        scene.to_csv(buffer, index=False, header=False)

        csv_text = buffer.getvalue()
        buffer.seek(0)

        return csv_text
    except Exception as error:
        return "Not Found", 404
    
@app.route('/api/sheets/current/<scene_id>', methods=['GET'])
def export_scene(scene_id):
    try:
        return tl.export_current_tl_scene(scene_id)
    except Exception as error:
        return "Not Found", 404

    
@app.route('/api/database/gen', methods=['GET'])
def renegare_db():
    try:
        tl.generate_db_file()
        return "Success", 200
    except Exception as error:
        return "Internal Server Error", 503

@app.route('/api/mrg/gen', methods=['GET'])
def generate_mrg():
    try:
        buffer = BytesIO()
        file_name, file_data = tl.generate_script_mrg()

        buffer.write(file_data)
        buffer.seek(0)

        return send_file(buffer, download_name=file_name, as_attachment=True)
    except Exception as error:
        return "Internal Server Error", 503

@app.route('/api/sheet/pull', methods=['POST'])
def upload_csv():
    try:
        csv_file = request.files['csv_file']
        tl.process_scene_csv(csv_file)
        
        return "Success", 200
    except Exception as e:
        # En caso de que se produzca un error, devolvemos una respuesta 500
        return "Error", 500


if __name__ == '__main__':
    app.run(debug=True)