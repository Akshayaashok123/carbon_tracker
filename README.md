# 🌱 Campus Carbon Tracker

A web application to help college students track their daily carbon footprint and compete on a campus-wide leaderboard for sustainability.

## 📁 Project Structure

```
carbon-tracker/
├── app.py                 # Flask backend server
├── requirements.txt       # Python dependencies
├── data/
│   └── users.json        # User data storage (auto-created)
├── static/
│   ├── css/
│   │   └── style.css     # Stylesheet
│   └── js/
│       └── main.js       # Frontend JavaScript
└── templates/
    └── index.html        # Main HTML template
```

## 🚀 Quick Start (3 Steps)

### Step 1: Install Python
- **Windows**: Download from [python.org](https://python.org)
- **Mac/Linux**: Python is usually pre-installed

Check if Python is installed:
```bash
python --version
```
(Should show Python 3.7 or higher)

### Step 2: Install Flask
Open terminal/command prompt in the `carbon-tracker` folder and run:
```bash
pip install -r requirements.txt
```

### Step 3: Run the Server
```bash
python app.py
```

Then open your browser and go to: **http://127.0.0.1:5000**

That's it! 🎉

---

## 📖 How to Use

### For Students:
1. Open the web app in your browser
2. (Optional) Enter your name to save to leaderboard
3. Select your daily activities:
   - How you commuted to campus
   - What you ate
   - Hours of electricity used
4. Click "Calculate My Footprint"
5. View your results, comparisons, and eco-tips
6. Click "Save to Leaderboard" to compete with classmates

### Features:
- ✅ **Real-time CO₂ calculation** based on daily activities
- ✅ **Personalized eco-tips** based on your choices
- ✅ **Visual comparisons** (driving km, trees needed, phone charges)
- ✅ **Weekly trend chart** to track progress
- ✅ **Campus-wide leaderboard** (lowest carbon wins!)
- ✅ **Responsive design** - works on phone, tablet, desktop

---

## 🛠️ How It Works (Technical)

### Frontend (HTML + CSS + JavaScript):
- **index.html**: Main user interface
- **style.css**: Beautiful gradient design with responsive layout
- **main.js**: Handles form submission, API calls, chart rendering

### Backend (Python + Flask):
- **app.py**: 
  - API endpoint `/api/calculate` - calculates carbon footprint
  - API endpoint `/api/save-entry` - saves user data
  - API endpoint `/api/leaderboard` - returns top 10 users
  - Stores data in `data/users.json` (simple file-based database)

### Data Flow:
```
User fills form → JavaScript sends data to /api/calculate 
→ Python calculates CO₂ → Returns result to frontend 
→ JavaScript displays results + tips → User saves to leaderboard 
→ Python updates users.json → Leaderboard refreshes
```

---

## 🎨 Customization

### Change Colors:
Edit `static/css/style.css`:
```css
/* Line 8: Main gradient background */
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);

/* Line 94: Button gradient */
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

### Change CO₂ Emission Factors:
Edit `app.py` or `templates/index.html`:
```python
# app.py - Line 58
electricity = electricity_hours * 0.3  # Change 0.3 to your value
```

```html
<!-- index.html - Lines 25-42 -->
<option value="0.5">Bus/Public Transport (0.5 kg CO₂)</option>
<!-- Change the values to match your research -->
```

### Add Your College Name:
Edit `templates/index.html`:
```html
<!-- Line 9 -->
<h1>🌱 [Your College] Carbon Tracker</h1>
```

---

## 📊 CO₂ Emission Factors Used

| Activity | CO₂ per unit |
|----------|-------------|
| Walk/Bicycle | 0 kg |
| Bus/Public Transport | 0.5 kg |
| Motorcycle | 2.3 kg |
| Car (alone) | 4.8 kg |
| Vegan meal | 0.8 kg |
| Veg meal | 1.5 kg |
| Chicken meal | 2.5 kg |
| Beef meal | 5.2 kg |
| Electricity | 0.3 kg per hour |

*Sources: EPA, IPCC, Carbon Footprint Calculator*

---

## 🏆 Hackathon Demo Tips

1. **Pre-populate the leaderboard**: Run the app and add 5-10 sample entries before your demo
2. **Use fullscreen (F11)** for a cleaner presentation
3. **Show different scenarios**:
   - Low carbon user (walk + vegan)
   - High carbon user (car alone + beef)
   - Show how tips change
4. **Highlight these features**:
   - "Works on any device - no app installation needed"
   - "100% free to build and deploy"
   - "Uses real EPA/IPCC data"
   - "Gamifies sustainability with leaderboard"

### Demo Script (30 seconds):
> "Hi! This is our Campus Carbon Tracker. Students log their daily activities — commute, food, electricity. The app calculates their CO₂ footprint instantly and gives personalized eco-tips. They can compete on a campus-wide leaderboard where the lowest carbon wins. It's built with Python and JavaScript, runs in any browser, and is 100% free to deploy. Watch — I'll show you."

---

## 🔧 Troubleshooting

**Error: "Flask is not installed"**
```bash
pip install Flask
```

**Error: "Port 5000 already in use"**
Change the port in `app.py` (last line):
```python
app.run(debug=True, host='0.0.0.0', port=8000)  # Changed to 8000
```

**Data not saving?**
Make sure the `data/` folder exists. The app auto-creates `users.json`.

**Leaderboard empty?**
Calculate your footprint, enter a name, and click "Save to Leaderboard" to add the first entry.

---

## 🚀 Deployment Options

### Option 1: Free Hosting on Render.com
1. Create account at [render.com](https://render.com)
2. Upload your code to GitHub
3. Connect GitHub repo to Render
4. Click "Deploy" → Your app is live!

### Option 2: Free Hosting on PythonAnywhere
1. Create account at [pythonanywhere.com](https://pythonanywhere.com)
2. Upload your files
3. Set up Flask app in dashboard
4. Your app is live at `yourname.pythonanywhere.com`

### Option 3: Run Locally
Just run `python app.py` on any computer with Python installed.

---

## 📝 Future Enhancements

Ideas to add if you have more time:
- [ ] User authentication (login/signup)
- [ ] Monthly/yearly statistics
- [ ] Share results on social media
- [ ] Compare with campus average
- [ ] Badges and achievements
- [ ] Carbon offset recommendations
- [ ] Mobile app version
- [ ] Integration with campus transport system

---

## 📄 License

Free to use for educational purposes. Made with 💚 for a greener campus.

---

## 🙋 Need Help?

Common questions:
- **Q: Do I need to know coding?** A: No! Just follow the Quick Start steps.
- **Q: Will this work on my laptop?** A: Yes! Windows, Mac, or Linux.
- **Q: Can I use this for my hackathon?** A: Absolutely! That's what it's for.
- **Q: How do I change the design?** A: Edit `static/css/style.css`.

---

## 🎯 What Makes This Project Special

✅ **Beginner-friendly** - Simple setup, well-commented code  
✅ **Fully functional** - Not just a mockup, it actually works  
✅ **Professional design** - Gradient UI, responsive layout  
✅ **Real data** - Uses actual EPA/IPCC carbon factors  
✅ **Gamified** - Leaderboard makes sustainability competitive  
✅ **Scalable** - Can add more features easily  
✅ **Zero cost** - Free to build and deploy  

---

**Good luck with your hackathon! 🚀🌱**
