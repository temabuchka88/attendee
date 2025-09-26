# simple_server.py
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging

# Базовая настройка для вывода информации в консоль
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class WebhookHandler(BaseHTTPRequestHandler):
    """
    Простой обработчик для приема и логирования POST-запросов (вебхуков).
    """
    def do_POST(self):
        # 1. Получаем длину тела запроса из заголовков
        content_length = int(self.headers.get('Content-Length', 0))
        
        # 2. Читаем тело запроса
        post_data = self.rfile.read(content_length)
        
        logging.info(f"--- Получен новый POST-запрос на адрес {self.path} ---")
        
        # 3. Пытаемся обработать тело запроса как JSON и красиво вывести
        try:
            json_data = json.loads(post_data)
            logging.info("Тело запроса (в формате JSON):")
            # Выводим отформатированный JSON
            print(json.dumps(json_data, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            # Если это не JSON, выводим как обычный текст
            logging.warning("Тело запроса не является валидным JSON. Вывод как текст:")
            print(post_data.decode('utf-8', errors='ignore'))
        
        # 4. Отправляем ответ 200 OK, подтверждая получение
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')

    def do_GET(self):
        """Отвечает на GET-запросы, чтобы можно было проверить в браузере, что сервер работает."""
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write("<h1>HTTP-сервер запущен.</h1><p>Ожидаю POST-запросы для их отображения в консоли.</p>")


def run_server(port=5005):
    """Функция для запуска сервера."""
    server_address = ('', port)  # Пустая строка означает "слушать на всех доступных IP"
    httpd = HTTPServer(server_address, WebhookHandler)
    
    logging.info(f"Запуск HTTP-сервера на порту {port}...")
    logging.info(f"Сервер доступен локально по адресу: http://localhost:{port}")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        # Позволяет остановить сервер через Ctrl+C
        pass
    
    httpd.server_close()
    logging.info("Сервер остановлен.")

if __name__ == '__main__':
    run_server()

