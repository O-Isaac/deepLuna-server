from libs.deepLuna.luna.translation_db import TranslationDb, ReadableExporter

import pandas as pd
import time

class TranslationUtils:
    "Utils for translation"
    def __init__(self, all_src_path = "allscr.mrg", script_text_path = "script_text.mrg", database_path = None):
        if (database_path is not None):
            self.db_tl = TranslationDb.from_file(database_path)
        else:
            self.db_tl = TranslationDb.from_mrg(all_src_path, script_text_path)

    def generate_csv_from_scene(self, scene_name):
        "Generate csv string to respond"
        scenes = self.db_tl.scene_names()
        scene_index = scenes.index(scene_name, 0)
        scene = scenes[scene_index]

        csv_matrix = [ ["hash", "en_text", "es_text"] ]
        lines = self.db_tl.lines_for_scene(scene)

        for line in lines:
            line_hash = self.db_tl.tl_line_with_hash(line.jp_hash)
            csv_matrix.append([line.jp_hash, line_hash.jp_text, ""])

        df = pd.DataFrame(csv_matrix)

        return df

    def process_scene_csv(self, lines_csv):
        try:
            df = pd.read_csv(lines_csv)

            for _indice, fila in df.iterrows():
                hash = fila["hash"]
                text = fila["es_text"]
                self.db_tl.set_translation_and_comment_for_hash(hash, text, "")

            print("[+] All rows are translated successfully ")
        except Exception as ex:
            print("[!] Something wrong with translation row process")
            print(ex)


    def generate_db_file(self):
        "Regenerate database"
        self.db_tl.to_file("database.json")

    def generate_script_mrg(self):
        "Generate Translated MRG file"
        current_time = time.strftime('%Y%m%d-%H%M%S')
        output_name = f"script_text_translated{current_time}.mrg"
        mzp_data = self.db_tl.generate_script_text_mrg()
        return [output_name, mzp_data]
    
    def export_current_tl_scene(self, scene_name):
        return ReadableExporter.export_text(self.db_tl, scene_name).encode('utf-8')