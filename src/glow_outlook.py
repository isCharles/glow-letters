"""Turn provider quality categories into plain viewing advice, not probabilities."""
import datetime as dt
import official_weather

ADVICE = {
    'zh': {'poor': '不烧', 'fair': '微烧', 'good': '小烧', 'great': '中烧', 'excellent': '大烧'},
    'en': {'poor': 'No glow', 'fair': 'Faint glow', 'good': 'Small glow',
           'great': 'Medium glow', 'excellent': 'Strong glow'},
}
CATEGORY = ADVICE['zh']


def result(event, hue_data=None, sb_data=None, solar=None, language='en', now=None):
    now = now or dt.datetime.now(official_weather.TZ)
    hue = next((row for row in (hue_data or {}).get('results', []) if row['event'] == event), {})
    category, source, score = None, None, None
    rows = [row for row in (sb_data or {}).get('results', []) if row.get('event') == event and row.get('available')]
    if hue.get('available'):
        category, source, score = hue['category'], 'Sunsethue', hue['quality']
        solar = hue['event_time']
    else:
        if rows:
            score = min(row['quality'] for row in rows)
            category = 'poor' if score < .05 else 'fair' if score < .4 else 'good' if score < .8 else 'great'
            source = 'SunsetBot'
    summary = ADVICE[language][category] if category else ('暂时不能判断，稍后再看' if language == 'zh' else 'Cannot judge this sky yet — check again later')
    if hue.get('reason') == 'not_configured' and source is None:
        summary = '连接 Sunsethue，获取观赏建议' if language == 'zh' else 'Connect Sunsethue for viewing advice'
    source_text = ''
    if source == 'Sunsethue':
        source_text = f'Sunsethue · {score*100:.0f}/100'
    elif source == 'SunsetBot':
        source_text = 'Sunsethue 暂不可用；参考 SunsetBot 地区预报' if language == 'zh' else 'Sunsethue unavailable; using the SunsetBot regional forecast'
        if language == 'zh':
            summary = {'poor': '不烧', 'fair': '小烧', 'good': '中烧', 'great': '大烧'}[category]
        else:
            summary = {'poor': 'No glow', 'fair': 'Small glow', 'good': 'Medium glow', 'great': 'Strong glow'}[category]
    medium = (score >= .6 if source == 'Sunsethue' else score >= .4) if score is not None else False
    disagreement = bool(source == 'Sunsethue' and medium and rows and min(row['quality'] for row in rows) < .4)
    if disagreement:
        source_text += ' · 预报分歧' if language == 'zh' else ' · forecasts disagree'
    sunrise = event.endswith('sunrise')
    # Nearby viewing starts at medium; trips/alarms require strong forecasts.
    # Keep the two providers' scales separate. Excellent's cutoff is provider-owned.
    worthy = (medium and category == 'excellent') if source == 'Sunsethue' else category == 'great'
    if category:
        if disagreement:
            summary = '预报有分歧，先不去' if language == 'zh' else 'Forecasts disagree — skip this one'
        elif worthy:
            summary += ('，值得早起' if sunrise else '，值得专程看') if language == 'zh' else (' — worth an early alarm' if sunrise else ' — worth a trip')
        elif medium:
            summary += ('，不必早起' if sunrise else '，顺路看') if language == 'zh' else (' — no early alarm needed' if sunrise else ' — nearby look')
    plan = ''
    if solar:
        center = dt.datetime.fromisoformat(solar)
        if center < now:
            summary = '这一场已过，看看下一场吧' if language == 'zh' else 'This one has passed — look ahead to the next sky'
        elif worthy and not disagreement:
            departure = center - dt.timedelta(minutes=25)
            if event.endswith('sunrise'):
                wake = departure - dt.timedelta(minutes=20)
                plan = (f'最晚 {wake:%H:%M} 起床，{departure:%H:%M} 出门。' if language == 'zh' else
                        f'Up by {wake:%H:%M}; leave by {departure:%H:%M}.')
            else:
                plan = f'建议最晚 {departure:%H:%M} 出门。' if language == 'zh' else f'Leave by {departure:%H:%M}.'
            plan += ('按准备20分钟、步行10分钟，提前15分钟到场估算；这不是最佳霞光时段预报。' if language == 'zh' else
                     ' Assumes 20 min to prepare, 10 min walking and arrival 15 min before the Sun event; not a peak-glow forecast.')
    return {'summary': summary, 'plan': plan, 'source_text': source_text, 'source': source, 'category': category}
