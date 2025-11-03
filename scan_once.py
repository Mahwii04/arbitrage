"""Run a single arbitrage scan within Flask app context"""
from app import create_app
from app.services.background_scanner import background_scanner

def main():
    app = create_app()
    # Ensure we don't auto-start background threads
    app.config['TESTING'] = True
    background_scanner.init_app(app)
    with app.app_context():
        background_scanner._perform_scan()

if __name__ == "__main__":
    main()