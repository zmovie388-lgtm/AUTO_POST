HAMBAWA AUTO POST BOT + HTML DASHBOARD

මෙය තනි HTML පමණක් නොවේ. Dashboard එක HTML/CSS/JavaScript වන අතර, සැබෑ Telegram Bot එක ක්‍රියාත්මක කිරීමට Python backend එක අවශ්‍යයි.

SETUP
1. ZIP එක extract කරන්න.
2. .env.example එක .env ලෙස copy/rename කරන්න.
3. BOT_TOKEN, ADMIN_ID, DASHBOARD_PASSWORD සහ FLASK_SECRET_KEY අගයන් පුරවන්න.
4. Python 3.11+ තිබෙන තැන:
   pip install -r requirements.txt
   python app.py
5. Dashboard: http://127.0.0.1:8080 (local) හෝ ඔබේ server address එකේ port 8080.
6. Telegram bot එකට private chat එකේ /start යවන්න.
7. Bot එක Groups වලට add කර Admin කරන්න. Send messages සහ Delete messages permissions දෙන්න.
8. Auto post කරන්න ඕන Text/Photo/Video/Document ආදිය bot එකට private message එකක් ලෙස යවන්න.
9. Dashboard එකේ Inline URL buttons labels/links set කර Save කරන්න.

FEATURES
- Bot එක admin කළ group එක auto-save කරයි.
- සෑම විනාඩි 10කටම bot එක කලින් යැවූ තමන්ගේ post එක delete කර නැවත යවයි.
- Dashboard එකෙන් Start/Stop, Post now, Clear post, group enable/disable සහ URL buttons manage කරන්න.
- SQLite මගින් settings, group list, template සහ buttons save වේ.

සීමා සහ ආරක්ෂාව
- වෙනත් bot එකක inline keyboard එක Telegram Bot API හරහා සාමාන්‍යයෙන් කියවිය නොහැක. Button labels සහ URLs Dashboard එකෙන් නැවත සකස් කරන්න.
- මේ version එක එක් message එකක් පමණක් template කරයි; albums/media groups නොවේ.
- 24/7 වැඩ කිරීමට process එක නොනවත්වා online තිබිය යුතුය. Free hosts sleep විය හැකියි.
- Public deploy එකකදී HTTPS/reverse proxy සහ production WSGI server භාවිතා කරන්න.
- .env, Bot Token සහ dashboard password කිසිවෙකුට share නොකරන්න.
