"""Private, dependency-free PDF reports. No filesystem or network operations.

A deliberately small PDF 1.7 writer for trusted report fields, not an HTML
renderer. Text is selectable, semantically tagged, and ordered for reading;
bookmarks, document language and explicit link labels aid navigation. This is
not a claim of independently certified PDF/UA or PDF/A conformance.
"""
from datetime import datetime, timezone
import re
from urllib.parse import quote, urlsplit

from scan_report import removal_guide, SITE_IDS
from search_diagnostics import search_diagnostic_text

# Standard PDF Helvetica metrics, in 1/1000 em for ASCII 32..126.
REGULAR = (278,278,355,556,556,889,667,191,333,333,389,584,278,333,278,278,
           556,556,556,556,556,556,556,556,556,556,278,278,584,584,584,556,1015,
           667,667,722,722,667,611,778,722,278,500,667,556,833,722,778,667,778,722,667,611,722,667,944,667,667,611,
           278,278,278,469,556,333,
           556,556,500,556,556,278,556,556,222,222,500,222,833,556,556,556,556,333,500,278,556,500,722,500,500,500,334,260,334,584)
BOLD = (278,333,474,556,556,889,722,238,333,333,389,584,278,333,278,278,
        556,556,556,556,556,556,556,556,556,556,333,333,584,584,584,611,975,
        722,722,722,722,667,611,778,722,278,556,722,611,833,722,778,667,778,722,667,611,722,667,944,667,667,611,
        333,278,333,584,556,333,
        556,611,556,611,556,333,611,611,278,278,556,278,889,611,611,611,611,389,556,333,611,556,778,556,556,500,389,280,389,584)
INK = '0.055 0.12 0.20'
MUTED = '0.25 0.32 0.39'
TEAL = '0.00 0.35 0.38'
PALE = '0.94 0.97 0.97'
RULE = '0.80 0.86 0.87'
WIDTH, HEIGHT, LEFT, RIGHT, BOTTOM = 612, 792, 48, 564, 68


def clean(value, limit=10000):
    """Never interpret report text as PDF operators, markup or invisible controls."""
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError('Invalid or oversized report field.')
    value = value.translate(str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"', '–': '-', '—': '-', '\u00a0': ' '}))
    value = ''.join(c if 32 <= ord(c) <= 126 else ' ' if c in '\n\r\t' else '\\u%04X' % ord(c) for c in value)
    return ' '.join(value.split())


def literal(value):
    return '(' + value.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') + ')'


def width(text, size, bold=False):
    metrics = BOLD if bold else REGULAR
    return sum(metrics[ord(c)-32] for c in text) * size / 1000


def wrap(value, size, available, bold=False):
    lines, current = [], ''
    for word in clean(value).split(' '):
        proposed = (current + ' ' + word).strip()
        if width(proposed, size, bold) <= available:
            current = proposed
            continue
        if current:
            lines.append(current)
            current = ''
        while width(word, size, bold) > available:
            cut = 1
            while cut < len(word) and width(word[:cut+1], size, bold) <= available:
                cut += 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines or ['']


def safe_url(value, host):
    """Only exact approved HTTPS hosts; no credentials, alternate ports or controls."""
    if not isinstance(value, str) or not 1 <= len(value) <= 2048 or any(ord(c) < 33 or ord(c) == 127 for c in value):
        raise ValueError('Unsafe report link.')
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != 'https' or parsed.hostname not in (host, 'www.' + host)
                or parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443)):
            raise ValueError('Unsafe report link.')
    except (ValueError, UnicodeError):
        raise ValueError('Unsafe report link.') from None
    # PDF URI strings are ASCII; preserve existing percent-encoding exactly.
    return quote(value, safe=":/?#[]@!$&'()*+,;=%-._~")


def stamp(value):
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError()
        return dt.astimezone(timezone.utc).strftime('%d %b %Y, %H:%M UTC')
    except (ValueError, AttributeError, TypeError):
        return 'Time not recorded'


class Document:
    def __init__(self, title, report_id, scope):
        self.title, self.report_id, self.scope = title, clean(report_id, 100), scope
        self.pages, self.bookmarks = [], []
        self.page = None
        self.y = 0
        self.section = ''

    def page_start(self, section):
        if len(self.pages) >= 80:
            raise ValueError('Report exceeds the safe page limit.')
        self.section = section
        self.page = {'ops': [], 'tags': [], 'links': []}
        self.pages.append(self.page)
        self.y = 710
        self.line('ScanPlus+', LEFT, 752, 17, True, TEAL, artifact=True)
        self.line(self.scope, 355, 755, 8, True, MUTED, artifact=True)
        self.line(section, 355, 741, 8, False, MUTED, artifact=True)
        self.rect(LEFT, 729, RIGHT-LEFT, 1, RULE)

    def ensure(self, needed):
        if self.y - needed < BOTTOM:
            self.page_start(self.section + ' (continued)' if not self.section.endswith('(continued)') else self.section)

    def rect(self, x, y, w, h, color):
        self.page['ops'].append(f'/Artifact BMC q {color} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f Q EMC')

    def line(self, text, x, y, size=10, bold=False, color=INK, tag='P', artifact=False, link=None):
        text = clean(text)
        if artifact:
            start = '/Artifact BMC'
        else:
            mcid = len(self.page['tags'])
            start = f'/{tag} <</MCID {mcid}>> BDC'
            self.page['tags'].append({'tag': tag, 'text': text, 'link': None})
        op = f'{start} BT /F{2 if bold else 1} {size} Tf {color} rg 1 0 0 1 {x:.2f} {y:.2f} Tm {literal(text)} Tj ET EMC'
        self.page['ops'].append(op)
        if link and not artifact:
            self.page['tags'][-1]['link'] = len(self.page['links'])
            self.page['links'].append({'uri': link, 'text': text, 'mcid': mcid,
                                       'rect': [x, y-2, x+width(text,size,bold), y+size]})

    def paragraph(self, text, size=10, bold=False, color=INK, tag='P', after=9, indent=0, link=None):
        lines = wrap(text, size, RIGHT-LEFT-indent, bold)
        leading = size * 1.43
        self.ensure(min(len(lines), 2) * leading + after)
        for line in lines:
            self.ensure(leading)
            self.line(line, LEFT+indent, self.y-size, size, bold, color, tag=tag, link=link)
            self.y -= leading
        self.y -= after

    def heading(self, text, level=2):
        self.ensure(65)
        if level == 1:
            self.bookmarks.append((clean(text), len(self.pages)-1, self.y))
        self.paragraph(text, size=28 if level == 1 else 14 if level == 2 else 11,
                       bold=True, tag='H'+str(level), after=15 if level == 1 else 9)

    def note(self, title, body):
        self.ensure(62)
        self.paragraph(title, size=10, bold=True, color=TEAL, after=5)
        self.paragraph(body, size=9, color=MUTED, after=14)

    def link(self, label, url, host):
        uri = safe_url(url, host)
        self.paragraph(label, size=9, bold=True, color=TEAL, tag='Link', after=4, link=uri)
        self.paragraph(uri, size=8, color=MUTED, after=11)

    def diagram_icon(self, kind, x, y):
        """Decorative vector icons; every meaning is repeated in tagged text.

        No screenshots, third-party logos, external assets or live form controls.
        Only fixed internal paths enter the content stream.
        """
        paths = {
            'record': '8 9 24 30 re S 13 31 m 25 31 l S 13 25 m 22 25 l S '
                      '13 19 m 19 19 l S 29 13 m 29 17.42 25.42 21 21 21 c '
                      '16.58 21 13 17.42 13 13 c 13 8.58 16.58 5 21 5 c '
                      '25.42 5 29 8.58 29 13 c S 27 7 m 35 -1 l S',
            'page': '4 3 34 34 re S 4 29 m 38 29 l S 10 33 m 11 33 l S '
                    '16 33 m 17 33 l S 15 12 m 30 27 l S 20 27 m 30 27 l 30 17 l S',
            'verify': '3 7 36 25 re S 3 32 m 21 18 l 39 32 l S '
                      '10 12 m 16 6 l 30 20 l S',
            'followup': '4 4 34 31 re S 4 27 m 38 27 l S 12 39 m 12 31 l S '
                        '30 39 m 30 31 l S 12 15 m 19 8 l 31 22 l S',
        }
        if kind not in paths:
            raise ValueError('Unsupported report illustration.')
        self.page['ops'].append(f'/Artifact BMC q {TEAL} RG 1.8 w 1 J 1 j '
                                f'1 0 0 1 {x:.2f} {y:.2f} cm {paths[kind]} Q EMC')

    def removal_roadmap(self):
        self.page_start('Illustrated removal roadmap')
        self.heading('Request removal, then verify', 1)
        self.paragraph('A visual guide to the manual process', size=13, color=MUTED, after=10)
        self.paragraph('Illustrations, not screenshots. Website layouts and verification requirements can change. '
                       'The broker forms have not been live-verified. Follow the current instructions on each official site.', size=9, color=MUTED, after=19)
        steps = (
            ('record', '1. Confirm the exact record',
             'Open the source listing and check that the name, location and other details are yours. '
             'A phone match alone does not prove ownership.'),
            ('page', '2. Open the official removal page',
             "Use the site's removal / privacy link in its source section. Follow the current official "
             'instructions; do not buy a paid lookup just to make a request.'),
            ('verify', '3. Submit and complete verification',
             'Supply only required details. Complete any CAPTCHA, email, phone or identity check yourself. '
             'ScanPlus does not submit the request for you.'),
            ('followup', '4. Save confirmation and recheck',
             "Keep the site's confirmation privately. After its stated processing period, revisit the exact "
             'listing. A request receipt is not proof of removal.'),
        )
        card_height, gap = 84, 14
        self.ensure(card_height*4 + gap*3)
        for index, (kind, title, body) in enumerate(steps):
            top = self.y
            self.rect(LEFT, top-card_height, RIGHT-LEFT, card_height, PALE)
            self.rect(LEFT, top-card_height, 3, card_height, TEAL)
            self.diagram_icon(kind, LEFT+19, top-61)
            self.line(title, LEFT+82, top-23, 12, True, TEAL, tag='H2')
            lines = wrap(body, 10, RIGHT-LEFT-98)
            if len(lines) > 3:
                raise ValueError('Illustrated instruction exceeds its card.')
            for row, text in enumerate(lines):
                self.line(text, LEFT+82, top-43-row*13.5, 10, color=INK)
            self.y -= card_height
            if index < len(steps)-1:
                # Down arrow joins steps but does not add a second reading order.
                x, y = LEFT+38, self.y
                self.page['ops'].append(f'/Artifact BMC q {TEAL} RG 1.4 w '
                                        f'{x} {y-2} m {x} {y-11} l '
                                        f'{x-3} {y-8} m {x} {y-11} l {x+3} {y-8} l S Q EMC')
                self.y -= gap
        self.y -= 18
        self.note('If a record is not yours', "Stop. Do not request deletion of another person's information. "
                  "If the form fails, use the official site's support or privacy contact rather than guessing a workaround.")
        self.paragraph('Removal from one site does not remove copies elsewhere or guarantee fewer unwanted calls. '
                       'No automatic removal or completed deletion is represented by this diagram.', size=9, color=MUTED)

    def finish(self):
        objects = []
        def add(value=''):
            objects.append(value.encode('ascii') if isinstance(value, str) else value)
            return len(objects)
        def put(index, value):
            objects[index-1] = value.encode('ascii') if isinstance(value, str) else value
        def ref(index): return f'{index} 0 R'
        def stream(raw): return b'<< /Length ' + str(len(raw)).encode() + b' >>\nstream\n' + raw + b'\nendstream'
        catalog, pages_id, struct, doc, parents, outline = [add() for _ in range(6)]
        # ASCII text has an explicit Unicode mapping for extraction/accessibility.
        cmap = '/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /ScanPlusUnicode def /CMapType 2 def 1 begincodespacerange <00> <FF> endcodespacerange 1 beginbfrange <20> <7E> <0020> endbfrange endcmap CMapName currentdict /CMap defineresource pop end end'
        cmap_id = add(stream(cmap.encode()))
        fonts = [add(f'<< /Type /Font /Subtype /Type1 /BaseFont /{name} /Encoding /WinAnsiEncoding /ToUnicode {ref(cmap_id)} >>') for name in ('Helvetica', 'Helvetica-Bold')]
        page_ids = [add() for _ in self.pages]
        tag_ids, parent_pairs = [], []
        annotation_key = len(self.pages)
        for pi, page in enumerate(self.pages):
            self.page = page
            self.rect(LEFT, 49, RIGHT-LEFT, .6, RULE)
            self.line('PRIVATE  |  ' + self.report_id, LEFT, 35, 7, color=MUTED, artifact=True)
            self.line(f'{pi+1} / {len(self.pages)}', 535, 35, 8, color=MUTED, artifact=True)
            content = add(stream('\n'.join(page['ops']).encode('ascii')))
            local_tags = [add() for _ in page['tags']]
            annotations = []
            for item in page['links']:
                annot = add(f'<< /Type /Annot /Subtype /Link /Rect [{" ".join(f"{n:.2f}" for n in item["rect"])}] /Border [0 0 0] /F 4 /P {ref(page_ids[pi])} /Contents {literal(item["text"])} /StructParent {annotation_key} /A << /S /URI /URI {literal(item["uri"])} >> >>')
                annotations.append(annot)
                parent_pairs.append(f'{annotation_key} {ref(local_tags[item["mcid"]])}')
                annotation_key += 1
            for ti, item in enumerate(page['tags']):
                kid = str(ti)
                if item['link'] is not None:
                    kid = f'[{ti} << /Type /OBJR /Obj {ref(annotations[item["link"]])} /Pg {ref(page_ids[pi])} >>]'
                put(local_tags[ti], f'<< /Type /StructElem /S /{item["tag"]} /P {ref(doc)} /Pg {ref(page_ids[pi])} /K {kid} >>')
            tag_ids.extend(local_tags)
            parent_pairs.append(f'{pi} [{" ".join(map(ref,local_tags))}]')
            put(page_ids[pi], f'<< /Type /Page /Parent {ref(pages_id)} /MediaBox [0 0 {WIDTH} {HEIGHT}] /Resources << /Font << /F1 {ref(fonts[0])} /F2 {ref(fonts[1])} >> >> /Contents {ref(content)} /StructParents {pi} /Tabs /S /Annots [{" ".join(map(ref,annotations))}] >>')
        parent_pairs.sort(key=lambda entry: int(entry.split()[0]))
        put(parents, f'<< /Nums [{" ".join(parent_pairs)}] >>')
        put(doc, f'<< /Type /StructElem /S /Document /P {ref(struct)} /K [{" ".join(map(ref,tag_ids))}] >>')
        put(struct, f'<< /Type /StructTreeRoot /K [{ref(doc)}] /ParentTree {ref(parents)} /ParentTreeNextKey {annotation_key} >>')
        outline_ids = [add() for _ in self.bookmarks]
        for i, (title, pi, y) in enumerate(self.bookmarks):
            siblings = (f' /Prev {ref(outline_ids[i-1])}' if i else '') + (f' /Next {ref(outline_ids[i+1])}' if i+1 < len(outline_ids) else '')
            put(outline_ids[i], f'<< /Title {literal(title)} /Parent {ref(outline)} /Dest [{ref(page_ids[pi])} /XYZ null {y:.2f} null]{siblings} >>')
        put(outline, f'<< /Type /Outlines /First {ref(outline_ids[0])} /Last {ref(outline_ids[-1])} /Count {len(outline_ids)} >>')
        put(pages_id, f'<< /Type /Pages /Kids [{" ".join(map(ref,page_ids))}] /Count {len(page_ids)} >>')
        put(catalog, f'<< /Type /Catalog /Pages {ref(pages_id)} /Lang (en-US) /MarkInfo << /Marked true >> /StructTreeRoot {ref(struct)} /Outlines {ref(outline)} /PageMode /UseOutlines /ViewerPreferences << /DisplayDocTitle true >> >>')
        info = add(f'<< /Title {literal(self.title)} /Author (ScanPlus) /Subject (Private bounded search report) /Creator (ScanPlus in-memory PDF renderer v1) >>')
        output = bytearray(b'%PDF-1.7\n%\xe2\xe3\xcf\xd3\n')
        offsets = [0]
        for i, obj in enumerate(objects,1):
            offsets.append(len(output)); output.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
        start = len(output)
        output.extend(f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode())
        for offset in offsets[1:]: output.extend(f'{offset:010d} 00000 n \n'.encode())
        output.extend(f'trailer\n<< /Size {len(objects)+1} /Root {ref(catalog)} /Info {ref(info)} >>\nstartxref\n{start}\n%%EOF\n'.encode())
        return bytes(output)


STATUS = {
    'match_needs_confirmation': ('Potential match', 'Exact phone text appeared in the checked index results. You must confirm whether each listing is yours.'),
    'not_found_in_checked_sources': ('No exact match in checked results', 'No exact phone match appeared in the returned index results. This does not prove your number is absent from this site.'),
    'source_unavailable': ('Unavailable - no conclusion', 'This source did not return a usable response. Do not interpret this as a clean result.'),
    'demo_example': ('Example listing - synthetic only', 'This is an illustration, not a finding about a real person. No live source was checked.'),
    'demo_not_checked': ('Not checked - synthetic only', 'No live source was checked. No absence or presence conclusion is possible.'),
}
REVIEWS = {'needs_confirmation': 'Needs your confirmation', 'confirmed_by_user': 'You marked this as yours', 'not_mine': 'You marked this as not yours'}


def report_pdf(report):
    """Render a current authorized report. Caller MUST enforce access and expiry."""
    sources = report['sources']
    if not isinstance(sources, list) or len(sources) > 3:
        raise ValueError('Invalid report coverage.')
    demo = report.get('demo') is True
    scope = ('STRIPE SANDBOX DEMO' if report.get('test_mode') else 'SYNTHETIC DEMO') if demo else 'PRIVATE NO-SMS SELF-TEST' if report.get('ownership_verified') is False else 'PRIVATE OWNER SELF-TEST' if report.get('test_scope') == 'private_owner' else 'LOCAL SELF-TEST'
    counts = {'matches': 0, 'checked': 0, 'unavailable': 0}
    seen = set()
    for source in sources:
        site, status = source['site'], source['status']
        if site not in SITE_IDS or site in seen or status not in STATUS or (status.startswith('demo_') != demo):
            raise ValueError('Invalid report source.')
        seen.add(site)
        candidates = source['candidates']
        if not isinstance(candidates,list) or len(candidates) > 10:
            raise ValueError('Invalid report candidates.')
        if status != 'match_needs_confirmation' and candidates:
            raise ValueError('Inconsistent report result.')
        counts['matches'] += len(candidates)
        counts['checked'] += status not in ('source_unavailable','demo_example','demo_not_checked')
        counts['unavailable'] += status == 'source_unavailable'
        for candidate in candidates:
            safe_url(candidate['source_url'], site)
    last_four = str(report.get('last_four', ''))
    if not re.fullmatch(r'[0-9]{4}', last_four):
        raise ValueError('Only a masked number may appear in report metadata.')
    doc = Document('ScanPlus | ' + ('Synthetic example report' if demo else 'Private search report'), report['report_id'], scope)
    doc.page_start('Search overview')
    doc.heading('Your search report', 1)
    doc.paragraph('Clear findings. Practical next steps.', size=13, color=MUTED, after=21)
    doc.paragraph('Number ending ' + last_four + '   |   ' + stamp(report.get('created_at')), size=10, bold=True, after=7)
    provider = 'No live search - synthetic fixtures' if demo else {'serper':'Serper / Google web index', 'brave':'Brave Search web index'}.get(report.get('search_provider'), 'Provider not recorded')
    doc.paragraph('Search method: ' + provider, size=9, color=MUTED, after=24)
    doc.rect(LEFT, doc.y-78, RIGHT-LEFT, 78, PALE)
    metrics = [(str(counts['matches']), 'Potential matches'), (f'{counts["checked"]} / {len(sources)}', 'Usable source responses'), (str(counts['unavailable']), 'Unavailable sources')]
    for i,(value,label) in enumerate(metrics):
        x = LEFT+16+i*172
        doc.line(value,x,doc.y-31,24,True,TEAL)
        doc.line(label,x,doc.y-56,8.5,False,MUTED)
    doc.y -= 100
    if report.get('ownership_verified') is False:
        doc.note('Ownership not verified', 'No SMS was sent. Phone ownership is self-attested, not verified. This private test does not confirm any listing belongs to you.')
    doc.heading('At a glance')
    for source in sources:
        guide = removal_guide(source['site'])
        doc.paragraph(guide['name'] + ': ' + STATUS[source['status']][0],size=10,bold=True,after=6)
    doc.y -= 10
    doc.note('Read the result correctly', 'A potential match is not a verified identity. No match is not proof of absence. An unavailable source supports no conclusion. No removal has been submitted or independently verified by ScanPlus.' if not demo else 'This report contains synthetic examples only. No real number was searched, no live source was checked, and no real removal was submitted or verified.')
    doc.note('Your next step', 'Review each source section. Confirm that a listing is yours before using its official manual removal path. Save any confirmation privately and revisit the exact listing after the site\'s stated processing period.')
    doc.note('Private download', 'Listing URLs can contain personal information. This file is not encrypted. Save and share it carefully; clearing or expiring the session does not delete downloaded copies.')
    doc.removal_roadmap()
    for source in sources:
        guide = removal_guide(source['site'])  # never trust a supplied destination/steps
        doc.page_start(guide['name'])
        doc.heading(guide['name'],1)
        doc.paragraph(STATUS[source['status']][0],size=12,bold=True,color=TEAL,after=8)
        doc.paragraph(STATUS[source['status']][1],size=10,after=10)
        doc.paragraph('Checked: ' + ('Not checked - demo' if demo else 'Query not attempted' if source.get('query_attempted') is False else stamp(source.get('checked_at'))),size=9,color=MUTED,after=8)
        if source.get('reason'):
            doc.paragraph('Availability note: ' + clean(source['reason'],100).replace('_',' '),size=9,color=MUTED,after=10)
        diagnostic = search_diagnostic_text(source.get('search_diagnostic'))
        if diagnostic:
            doc.paragraph(diagnostic, size=9, color=MUTED, after=10)
        if source['candidates']:
            doc.heading('Indexed listing evidence')
        for i,candidate in enumerate(source['candidates'],1):
            doc.ensure(120)
            doc.heading('Listing ' + str(i),3)
            doc.link('Open listing ' + str(i) + ' on ' + guide['name'] + ' (external)',candidate['source_url'],source['site'])
            doc.paragraph('Evidence: exact phone text was present in the search index. The listing page and identity have not been independently verified.',size=9,after=7)
            review = candidate.get('match_review')
            doc.paragraph('Your review: '+REVIEWS.get(review,'Unknown - review again'),size=9,bold=True,after=5)
            checklist = 'You recorded a manual request; not verified by ScanPlus' if candidate.get('manual_action') == 'user_recorded_request' else 'No manual request recorded'
            doc.paragraph('Your checklist: '+checklist,size=9,after=10)
            if review == 'not_mine':
                doc.paragraph('Do not request removal of this record.',size=9,bold=True,after=12)
        doc.heading('How to request removal')
        doc.paragraph('Manual guidance only. Current form workflow not independently verified.',size=9,bold=True,after=8)
        doc.link('Official '+guide['name']+' removal / privacy page (external)',guide['url'],source['site'])
        for i,step in enumerate(guide['steps'],1):
            doc.paragraph(str(i)+'. '+step,size=10,after=6)
        doc.note('Before you submit',guide['safety_notice'])
        doc.note('After you submit',guide['follow_up'])
        doc.paragraph('Destination evidence: California Data Broker Registry, updated '+guide['registry_updated']+'; broker '+guide['registry_broker_id']+'. Mapping reviewed '+guide['reviewed_at']+'. This evidence confirms a destination, not the current form or a removal outcome.',size=8,color=MUTED,after=7)
        doc.link('View destination evidence (California registry)',guide['source_url'],'cppa.ca.gov')
    doc.page_start('Scope and privacy')
    doc.heading('Scope & privacy',1)
    doc.heading('What this report covers')
    doc.paragraph(report['coverage'],size=10)
    doc.note('What it does not establish','This is not a full Internet scan, a direct broker database search, an identity check, or proof that your information is absent. Indexed results can be stale, incomplete or refer to a prior holder of a phone number. This report does not identify the source of unwanted calls or promise fewer calls.')
    doc.heading('How to interpret actions')
    doc.paragraph('Where performed, phone verification establishes current control, not ownership of every listing. Your listing review and manual-request checklist are self-reported. A request receipt, checked box or missing search result does not prove removal. ScanPlus does not submit requests from this report.',size=10)
    doc.paragraph('Self-service requests are normally free. Do not buy a paid lookup merely to use these guides. Complete any CAPTCHA, email, phone or identity check yourself using the site\'s current instructions.',size=10)
    doc.heading('Deletion API status')
    doc.paragraph('Research review: 8 November 2026. No authorized public deletion API verified for Spokeo, Whitepages or TruePeopleSearch. This does not rule out private partner arrangements. A search or data API is not permission to submit deletions. ScanPlus provides manual guidance only.', size=9, after=13)
    doc.heading('Keep the report private')
    doc.paragraph(report.get('privacy_notice','Downloads may contain personal information in listing URLs and remain on your device after Clear or expiry.'),size=10)
    doc.paragraph('The PDF is generated in server memory without a separate PDF service. It contains a masked number in the summary, but source URLs can contain a full number or other personal information. Opening a link deliberately contacts that site; links are not opened during generation. This PDF is not encrypted or digitally signed.',size=10)
    doc.paragraph(report.get('payment_notice','No checkout or payment is part of this self-test.'),size=9,color=MUTED,after=20)
    doc.note('Report identity','Report ID: '+doc.report_id+'. This is a snapshot of the saved search and checklist at download time. New checklist changes require a new download. Dates are shown in UTC.')
    return doc.finish()


def demo_report_pdf(report):
    """Adapt synthetic demo schema without converting examples into real matches."""
    if report.get('demo') is not True:
        raise ValueError('Only explicit synthetic reports can use this adapter.')
    id_to_site = {value:key for key,value in SITE_IDS.items()}
    sources = []
    for item in report.get('providers',[]):
        site = id_to_site.get(item['id'])
        if site is None: raise ValueError('Unsupported demo source.')
        sources.append({'site':site,'status':'demo_example' if item.get('status')=='example_listing' else 'demo_not_checked','candidates':[]})
    return report_pdf({'demo':True,'test_mode':report.get('test_mode',False),'report_id':report['report_id'],'last_four':str(report['phone'])[-4:],
                       'created_at':report.get('created_at'),'search_provider':'demo','sources':sources,
                       'coverage':'Synthetic examples for '+str(len(sources))+' supported source guides. No live web query, broker search or real phone check occurred.',
                       'privacy_notice':'Keep downloaded reports private. Downloads remain on your device after the demo session is cleared or expires.',
                       'payment_notice':'Synthetic demo only. No real charge or refund is represented by this report.'})
