import logging
from io import StringIO

def create_logger(sheet_id):
    log_stream = StringIO()    
    logging.basicConfig(stream=log_stream, level=logging.INFO, format=f'[{sheet_id}] %(asctime)s - %(levelname)s - %(message)s')
    
    return log_stream, logging