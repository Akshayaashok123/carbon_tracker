@echo off
echo ========================================
echo  Campus Carbon Tracker Server
echo ========================================
echo.
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting server...
echo Open http://127.0.0.1:5000 in your browser
echo Press CTRL+C to stop the server
echo.
python app.py
pause
