from libs.deepLuna.luna.translation_db import TranslationDb, ReadableExporter, RubyUtils
from libs.deepLuna.luna.constants import Constants
from math import isnan, ceil
from textwrap import wrap
from difflib import get_close_matches
from tempfile import NamedTemporaryFile

import pandas as pd
import time
import os

class Color:
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    ENDC = '\033[0m'

    def __init__(self, color):
        self.color = color

    def __call__(self, text):
        return f"{self.color}{text}{Color.ENDC}"

class Utils:
    @staticmethod
    def check_int_or_float( value):
        return isinstance(value, int) or isinstance(value, float)

    @staticmethod
    def is_nan(value):
        return isnan(value)

    @staticmethod
    def adjust_text_width(text):
        fix_text = text.replace("\r", "\n")
        wrapped_text = wrap(fix_text, width=Constants.CHARS_PER_LINE)
        
        if len(wrapped_text) == 1:
            return wrapped_text[0]

        return "\n ".join(wrapped_text).strip().replace("  ", " ")
    

class TranslationUtils:
    "Utils for translation"
    def __init__(self, all_src_path = "allscr.mrg", script_text_path = "script_text.mrg", database_path = None):
        RubyUtils.ENABLE_PUA_CODES = True

        if (database_path is not None):
            self.db_tl = TranslationDb.from_file(database_path)
        else:
            self.db_tl = TranslationDb.from_mrg(all_src_path, script_text_path)

    def get_scene(self, scene_name: str):
        scenes = self.db_tl.scene_names()
        
        for scene in scenes:
            if scene_name == scene:
                return scene
            
        return None

    def generate_csv_from_scene(self, scene_name):
        "Generate csv string to respond"
        scene = self.get_scene(scene_name)
        csv = [ ["hash", "english"] ]
        text_commands = self.db_tl.lines_for_scene(scene)

        for text_command in text_commands:
            line_hash = text_command.jp_hash
            line_text = self.db_tl.tl_line_for_cmd(text_command).jp_text

            csv.append([line_hash, line_text])

        df = pd.DataFrame(csv)

        return df

    def process_scene_csv(self, lines_csv, sceneId):
        try:
            df = pd.read_csv(lines_csv)

            for _indice, fila in df.iterrows():
                line_hash: str = fila["hash"]
                line_text_translated: str = fila["spanish"]


                if Utils.check_int_or_float(line_text_translated) and Utils.is_nan(line_text_translated):
                    print(Color(Color.YELLOW)(f"{sceneId} | {line_hash} | Missing line skipping..."))
                    continue
                
                self.db_tl.set_translation_and_comment_for_hash(line_hash, Utils.adjust_text_width(line_text_translated), "")
                print(Color(Color.BLUE)(f"{sceneId} | {line_hash} | line successfully replaced."))
        except Exception as ex:
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