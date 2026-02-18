import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import GenericLoader, LanguageParser
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

class LocalCodeRAG:
    def __init__(self, project_path, db_path="./chroma_db"):
        self.project_path = project_path
        self.db_path = db_path
        
        # 1. 무료 로컬 임베딩 모델 설정 (HuggingFace)
        # 'all-MiniLM-L6-v2'는 용량이 작고 속도가 매우 빨라 로컬용으로 제격이야.
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

    def index_projects(self):
        """프로젝트 코드를 읽어서 Vector DB에 저장"""
        print(f"[{self.project_path}] 코드 인덱싱 시작...")

        # 2. 코드 로더 설정 (Python, JS, Java 등 확장자 지정)
        loader = GenericLoader.from_path(
            self.project_path,
            glob="**/*",
            suffixes=[ ".ts"], # 네 프로젝트 언어에 맞춰 추가/삭제해
            parser=LanguageParser()
        )
        docs = loader.load()

        # 3. 코드 단위로 쪼개기 (RecursiveCharacterTextSplitter)
        # 코드는 일반 텍스트와 달라서 문법에 맞춰 자르는 게 중요해.
        splitter = RecursiveCharacterTextSplitter.from_language(
            language=Language.TYPESCRIPT, # 주요 언어 설정
            chunk_size=1000, 
            chunk_overlap=100
        )
        split_docs = splitter.split_documents(docs)

        # 4. Chroma DB 생성 및 로컬 저장
        self.vectorstore = Chroma.from_documents(
            documents=split_docs,
            embedding=self.embeddings,
            persist_directory=self.db_path
        )
        print(f"인덱싱 완료! 총 {len(split_docs)}개의 코드 조각이 저장되었습니다.")

    def search(self, query, k=3):
        """질문(이슈)과 관련된 코드 조각 찾기"""
        # 저장된 DB 로드
        db = Chroma(
            persist_directory=self.db_path, 
            embedding_function=self.embeddings
        )
        
        # 유사도 검색 수행
        results = db.similarity_search(query, k=k)
        
        return results

# --- 실행 예시 ---
if __name__ == "__main__":
    # 네 프로젝트 폴더 경로를 넣어줘 (예: './my_project')
    MY_PROJECT = os.path.expanduser("~/Desktop/aba/ababe")
    
    rag = LocalCodeRAG(MY_PROJECT)
    
    # [처음 한 번만 실행] 인덱싱 프로세스
    # rag.index_projects() 
    
    # [검색 테스트]
    issue = "로그인 API에서 응답 값에 유저 생년월일을 추가하고 싶어"
    relevant_codes = rag.search(issue)

    print("\n[검색 결과]")
    for i, doc in enumerate(relevant_codes):
        print(f"[{i+1}] 파일: {doc.metadata['source']}")
        print(f"내용 요약: {doc.page_content[:100]}...")
        print("-" * 30)