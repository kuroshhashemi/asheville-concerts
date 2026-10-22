"""Read adult legends across whatever sections the current seat map offers."""
def collect(page):
    from concert_discovery.prices import from_ticket_markup
    sections=page.locator('#tn-syos-screen-list')
    sections.wait_for(state='visible',timeout=30000)
    names=sections.get_by_role('button').all_text_contents()
    prices=[]
    for index,name in enumerate(dict.fromkeys(n.strip() for n in names if n.strip())):
        if index:page.get_by_role('button',name='Change Section',exact=True).click(timeout=10000)
        page.locator('#tn-syos-screen-list').get_by_role('button',name=name,exact=True).click(timeout=10000)
        legend=page.get_by_role('button',name='Pricing Legend',exact=True)
        legend.wait_for(timeout=10000)
        if legend.get_attribute('aria-expanded')!='true':legend.click(timeout=10000)
        page.locator('#tn-syos-legend-container').wait_for(timeout=10000)
        if page.get_by_role('checkbox').count():
            price=from_ticket_markup(page.url,page.content())
            if price:prices.append(price)
    if not prices:return None
    return {'min':min(p['min'] for p in prices),'max':max(p['max'] for p in prices),'from_price':True}
