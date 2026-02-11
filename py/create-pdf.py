from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_JUSTIFY
import random

# PDF 파일 생성
pdf_file = "./lorem_ipsum_30pages.pdf"
doc = SimpleDocTemplate(pdf_file, pagesize=A4,
                        rightMargin=2*cm, leftMargin=2*cm,
                        topMargin=2*cm, bottomMargin=2*cm)

# 스타일 설정
styles = getSampleStyleSheet()
style_normal = ParagraphStyle(
    'CustomNormal',
    parent=styles['Normal'],
    fontSize=11,
    leading=14,
    alignment=TA_JUSTIFY,
    spaceAfter=12
)

style_heading = ParagraphStyle(
    'CustomHeading',
    parent=styles['Heading1'],
    fontSize=16,
    leading=20,
    spaceAfter=12
)

# 로렘입숨 텍스트 템플릿
lorem_paragraphs = [
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.",
    "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.",
    "Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.",
    "Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia consequuntur magni dolores eos qui ratione voluptatem sequi nesciunt. Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit.",
    "At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis praesentium voluptatum deleniti atque corrupti quos dolores et quas molestias excepturi sint occaecati cupiditate non provident, similique sunt in culpa qui officia deserunt mollitia animi.",
    "Temporibus autem quibusdam et aut officiis debitis aut rerum necessitatibus saepe eveniet ut et voluptates repudiandae sint et molestiae non recusandae. Itaque earum rerum hic tenetur a sapiente delectus, ut aut reiciendis voluptatibus maiores alias consequatur aut perferendis doloribus asperiores repellat."
]

# 문서 내용 생성
story = []

for page_num in range(1, 31):
    # 페이지 제목
    story.append(Paragraph(f"Page {page_num} - Lorem Ipsum", style_heading))
    story.append(Spacer(1, 0.3*cm))
    
    # 각 페이지에 4-6개의 단락 추가
    num_paragraphs = random.randint(4, 6)
    for _ in range(num_paragraphs):
        para_text = random.choice(lorem_paragraphs)
        story.append(Paragraph(para_text, style_normal))
        story.append(Spacer(1, 0.2*cm))
    
    # 마지막 페이지가 아니면 페이지 나누기
    if page_num < 30:
        story.append(PageBreak())

# PDF 생성
doc.build(story)

print(f"30페이지 로렘입숨 PDF가 생성되었습니다: {pdf_file}")