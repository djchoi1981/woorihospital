from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.orm import declarative_base
import os
import qrcode
from io import BytesIO
from fastapi.responses import StreamingResponse

# Database Setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./contact.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ContactInfo(Base):
    __tablename__ = "contact_info"
    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String, default="010-0000-0000")
    kakao_url = Column(String, default="https://open.kakao.com/o/...")

Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize default contact info if not exists on startup
    db = SessionLocal()
    info = db.query(ContactInfo).first()
    if not info:
        default_info = ContactInfo(phone_number="010-1234-5678", kakao_url="https://open.kakao.com/")
        db.add(default_info)
        db.commit()
    db.close()
    yield

app = FastAPI(lifespan=lifespan)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Templates & Static
os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)
templates = Jinja2Templates(directory="templates")

ADMIN_PASSWORD = "admin" # 기본 비밀번호 설정

@app.get("/", response_class=HTMLResponse)
async def read_contact(request: Request, db: Session = Depends(get_db)):
    info = db.query(ContactInfo).first()
    return templates.TemplateResponse(request=request, name="index.html", context={"info": info})

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, db: Session = Depends(get_db)):
    if request.cookies.get("admin_auth") != "true":
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    info = db.query(ContactInfo).first()
    # 도메인이 배포된 주소여야 진짜 QR 코드가 동작함 (로컬 테스트용)
    host_url = str(request.base_url) 
    return templates.TemplateResponse(request=request, name="admin.html", context={"info": info, "host_url": host_url})

@app.post("/admin")
async def update_contact(
    request: Request, 
    phone_number: str = Form(...), 
    kakao_url: str = Form(...),
    db: Session = Depends(get_db)
):
    if request.cookies.get("admin_auth") != "true":
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    info = db.query(ContactInfo).first()
    if info:
        info.phone_number = phone_number
        info.kakao_url = kakao_url
        db.commit()
        
    return RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/admin", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="admin_auth", value="true")
        return response
    return templates.TemplateResponse(request=request, name="login.html", context={"error": "비밀번호가 일치하지 않습니다."})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("admin_auth")
    return response

@app.get("/qr_code")
async def generate_qr_code(request: Request):
    # 이 서버의 루트 주소를 가리키는 QR 코드 생성
    base_url = str(request.base_url)
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(base_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    return StreamingResponse(buf, media_type="image/png")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
