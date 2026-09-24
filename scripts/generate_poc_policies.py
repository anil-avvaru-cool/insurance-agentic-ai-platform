"""Build the AWS POC policy documents from their reviewed source."""

import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1] / 'data' / 'sample_insurance_policies'
NAVY = colors.HexColor('#193347')
GRAY = colors.HexColor('#52616B')
LIGHT = colors.HexColor('#EEF2F5')
LABELS = {
    'bodily_injury': 'Bodily injury liability',
    'property_damage': 'Property damage liability',
    'collision': 'Collision', 'comprehensive': 'Comprehensive',
    'building': 'Coverage A | Dwelling',
    'belongings': 'Coverage C | Personal property',
    'deductible': 'Section I deductible', 'exclusions': 'Exclusions',
}


def main():
    body = ParagraphStyle('body', fontName='Helvetica', fontSize=9, leading=12,
                          textColor=NAVY, spaceAfter=6)
    small = ParagraphStyle('small', parent=body, fontSize=8, leading=10, spaceAfter=0)
    title = ParagraphStyle('title', parent=body, fontName='Helvetica-Bold',
                           fontSize=23, leading=27, spaceAfter=5)
    label = ParagraphStyle('label', parent=body, fontName='Helvetica-Bold',
                           fontSize=9, leading=12, spaceBefore=5, spaceAfter=3)
    eyebrow = ParagraphStyle('eyebrow', parent=small, textColor=GRAY, spaceAfter=4)

    def p(text, style=body):
        return Paragraph(escape(text), style)

    for document in json.loads((ROOT / 'documents.json').read_text()):
        metadata = document['metadata']
        passages = {item['id']: item['text'] for item in document['passages']}
        target = ROOT / f"{metadata['document_id']}.pdf"
        story = [p('PERSONAL INSURANCE  /  POLICY DECLARATIONS', eyebrow),
                 p(metadata['product_name'], title),
                 p('Coverage schedule and policy provisions', body), Spacer(1, 6)]
        declarations = Table([
            [p('NAMED INSURED', eyebrow), p('POLICY NUMBER', eyebrow)],
            [p(document['customer_name'], label), p(metadata['policy_id'], label)],
            [p('POLICY PERIOD', eyebrow), p('EDITION', eyebrow)],
            [p('January 1, 2026 - December 31, 2026', small),
             p('01/2026  |  Version ' + metadata['version'], small)],
        ], colWidths=[310, 218])
        declarations.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), LIGHT),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story += [declarations, Spacer(1, 10), p(passages['scope'], small),
                  Spacer(1, 5), p('COVERAGE SCHEDULE', label)]
        rows = [[p('Coverage', label), p('Limit of insurance', label), p('Deductible', label)]]
        for key in (['bodily_injury', 'property_damage', 'collision', 'comprehensive']
                    if metadata['lob'] == 'auto' else ['building', 'belongings']):
            amounts = re.findall(r'\$[\d,]+', passages[key])
            if key == 'bodily_injury':
                limit, deductible = f'{amounts[0]} each person / {amounts[1]} each accident', 'None'
            elif key == 'property_damage':
                limit, deductible = f'{amounts[0]} each accident', 'None'
            elif key in ('collision', 'comprehensive'):
                limit, deductible = 'Actual cash value', amounts[0]
            else:
                limit = f'{amounts[0]} each covered loss'
                deductible = re.search(r'\$[\d,]+', passages['deductible']).group() + '*'
            rows.append([p(LABELS[key], small), p(limit, small), p(deductible, small)])
        schedule = Table(rows, colWidths=[170, 262, 96])
        schedule.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), LIGHT),
            ('LINEBELOW', (0, 0), (-1, 0), 0.7, NAVY),
            ('LINEBELOW', (0, 1), (-1, -1), 0.4, colors.HexColor('#D7DEE3')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story += [schedule, Spacer(1, 6)]
        if metadata['lob'] == 'property':
            story.append(p('* One deductible applies to the combined payment for the same covered loss.', small))
        story.append(p('POLICY PROVISIONS', label))
        for key, text in passages.items():
            if key in ('scope', 'unknowns'):
                continue
            story.append(Paragraph(f'<b>{escape(LABELS[key])}.</b> {escape(text)}', body))
        story += [Spacer(1, 4), p('DOCUMENT REFERENCE', eyebrow)]
        # Keep exact labels available for the later deterministic extraction step.
        for keys in [('document_id', 'owner_id'), ('policy_id', 'lob', 'version'),
                     ('product_name', 'effective_date')]:
            story.append(p('    |    '.join(f'{key}: {metadata[key]}' for key in keys), small))

        def footer(canvas, doc):
            canvas.saveState()
            canvas.setStrokeColor(NAVY)
            canvas.line(42, 39, 570, 39)
            canvas.setFont('Helvetica', 7)
            canvas.setFillColor(GRAY)
            canvas.drawString(42, 26, 'Sample document for demonstration only. Not an insurance contract.')
            canvas.drawRightString(570, 26, f"{metadata['policy_id']}  |  {doc.page}")
            canvas.restoreState()

        SimpleDocTemplate(str(target), pagesize=letter, rightMargin=42, leftMargin=42,
                          topMargin=32, bottomMargin=49, title=metadata['product_name'],
                          author='Policy Services', invariant=1).build(
                              story, onFirstPage=footer, onLaterPages=footer)
        print(target.relative_to(ROOT.parent.parent))


if __name__ == '__main__':
    main()
