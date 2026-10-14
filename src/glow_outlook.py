"""Turn provider quality categories into plain viewing advice, not probabilities."""
import datetime as dt
import official_weather

ADVICE = {
    'zh': {'poor': '偏弱，不建议专程去看', 'fair': '一般，顺路看看就好',
           'good': '小烧候选，可以出去看看', 'great': '中烧候选，值得留意', 'excellent': '大烧候选，值得留出时间'},
    'en': {'poor': 'Subtle sky — skip the special trip', 'fair': 'Take a look if you are nearby',
           'good': 'Looking promising — head outside', 'great': 'Worth making time for',
           'excellent': 'Make time for this sky'},
}
CATEGORY = {'poor': '偏弱', 'fair': '一般', 'good': '小烧候选', 'great': '中烧候选', 'excellent': '大烧候选'}


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
        grade = CATEGORY[category] if language == 'zh' else category.title()
        source_text = (f'Sunsethue {category.title()} → {grade} · 质量评分 {score*100:.0f}/100（中文展示映射，不是发生概率）' if language == 'zh' else
                       f'Sunsethue forecast: {grade} · quality {score*100:.0f}/100 (not a probability)')
    elif source == 'SunsetBot':
        source_text = 'Sunsethue 暂不可用；参考 SunsetBot 地区预报' if language == 'zh' else 'Sunsethue unavailable; using the SunsetBot regional forecast'
        if language == 'zh':
            summary = {'poor': '偏弱，不建议专程去看', 'fair': '小烧，顺路看看就好',
                       'good': '中烧候选，可以出去看看', 'great': '大烧候选，值得留意'}[category]
    disagreement = source == 'Sunsethue' and category in ('good', 'great', 'excellent') and rows and min(row['quality'] for row in rows) < .4
    if disagreement:
        summary = '预报有分歧，顺路看看，先不专程赶去' if language == 'zh' else 'Forecasts differ — take a nearby look, skip the special trip'
        source_text += ('；SunsetBot 地区预报较弱，评分体系不同' if language == 'zh' else '; SunsetBot regional outlook is weaker; scores use different scales')
    sunrise = event.endswith('sunrise')
    # Provider categories are presentation mappings, not calibrated burn levels.
    # Only the strongest category warrants an early alarm; sunset needs Great+.
    worthy = category == 'excellent' if sunrise else category in ('great', 'excellent')
    if source == 'SunsetBot':
        worthy = category == 'great' if sunrise else category in ('good', 'great')
    if not disagreement and category:
        if sunrise and not worthy:
            summary += '，不必特意早起' if language == 'zh' else ' — no early alarm needed'
        elif not sunrise and not worthy:
            summary += '，顺路看，不专程赶去' if language == 'zh' else ' — take a nearby look, skip the special trip'
        elif language == 'zh':
            summary += '，可以为它早起' if sunrise else '，值得专程去看'
    plan = ''
    if solar:
        center = dt.datetime.fromisoformat(solar)
        if center < now:
            summary = '这一场已过，看看下一场吧' if language == 'zh' else 'This one has passed — look ahead to the next sky'
        elif disagreement:
            plan = '先不为这一场安排专程出行。' if language == 'zh' else 'Avoid planning a special trip for this one.'
        elif worthy:
            departure = center - dt.timedelta(minutes=25)
            if event.endswith('sunrise'):
                wake = departure - dt.timedelta(minutes=20)
                plan = (f'最晚 {wake:%H:%M} 起床，{departure:%H:%M} 出门。' if language == 'zh' else
                        f'Up by {wake:%H:%M}; leave by {departure:%H:%M}.')
            else:
                plan = f'建议最晚 {departure:%H:%M} 出门。' if language == 'zh' else f'Leave by {departure:%H:%M}.'
            plan += ('按准备20分钟、步行10分钟，提前15分钟到场估算；这不是最佳霞光时段预报。' if language == 'zh' else
                     ' Assumes 20 min to prepare, 10 min walking and arrival 15 min before the Sun event; not a peak-glow forecast.')
        elif category:
            plan = ('不必为这一场特意早起。' if event.endswith('sunrise') else '不用赶路，顺手抬头看看。') if language == 'zh' else 'No need to rearrange your day for this one.'
    return {'summary': summary, 'plan': plan, 'source_text': source_text, 'source': source, 'category': category}
