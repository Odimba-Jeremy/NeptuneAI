"""
API BACKEND COMPLET POUR ANALYSE TIKTOK
FastAPI + Apify
Fonctionnalités:
- Transcription vidéo TikTok
- Traduction multilingue (24 langues)
- Détection de texte IA
- Recherche d'influenceurs

Endpoint: POST /analyze
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import requests
import time
import json
import asyncio
from datetime import datetime
from enum import Enum

# ============================================
# CONFIGURATION
# ============================================

API_KEY = "apify_api_0G0uTXgK8UaKvTbPrRwcy7OMcKBANG0aV4zq"

ACTORS = {
    "transcriber": "agentx/tiktok-video-transcriber",
    "ai_detector": "easyapi/ai-content-detector",
    "deepl": "tkapler/deepl-actor",
    "influencer_finder": "apify/influencer-discovery-agent"
}

# Langues disponibles pour la traduction
AVAILABLE_LANGUAGES = {
    "FR": "Français",
    "EN": "English", 
    "ES": "Español",
    "DE": "Deutsch",
    "IT": "Italiano",
    "PT": "Português",
    "NL": "Nederlands",
    "RU": "Русский",
    "JA": "日本語",
    "KO": "한국어",
    "ZH": "中文",
    "AR": "العربية",
    "HI": "हिन्दी",
    "TR": "Türkçe",
    "PL": "Polski",
    "UK": "Українська",
    "SV": "Svenska",
    "DA": "Dansk",
    "NO": "Norsk",
    "FI": "Suomi",
    "CS": "Čeština",
    "HU": "Magyar",
    "EL": "Ελληνικά",
    "HE": "עברית"
}

# ============================================
# MODÈLES PYDANTIC (Validation des requêtes)
# ============================================

class AnalyzeRequest(BaseModel):
    """Requête d'analyse TikTok"""
    tiktok_url: str = Field(..., description="URL de la vidéo TikTok")
    
    # Options
    translate: bool = Field(True, description="Activer la traduction")
    target_languages: Optional[List[str]] = Field(
        ["FR", "EN", "ES", "DE", "IT"], 
        description="Langues pour la traduction (codes ISO)"
    )
    detect_ai: bool = Field(True, description="Détecter si le texte est généré par IA")
    find_influencers: bool = Field(True, description="Trouver des influenceurs similaires")
    
    # Pour la recherche d'influenceurs
    brand_description: Optional[str] = Field(None, description="Description de votre marque")
    max_influencers: int = Field(10, description="Nombre maximum d'influenceurs à trouver")

    def validate_languages(self):
        """Valide que les langues demandées sont supportées"""
        for lang in self.target_languages:
            if lang not in AVAILABLE_LANGUAGES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Langue non supportée: {lang}. Langues disponibles: {list(AVAILABLE_LANGUAGES.keys())}"
                )


class AnalysisStatusResponse(BaseModel):
    """Statut d'une analyse"""
    run_id: str
    status: str
    created_at: str
    result_url: Optional[str] = None


class AnalysisResultResponse(BaseModel):
    """Résultat complet d'analyse"""
    run_id: str
    tiktok_url: str
    status: str
    transcript: Optional[str] = None
    ai_score: Optional[float] = None
    ai_is_ai_generated: Optional[bool] = None
    translations: Optional[Dict[str, str]] = None
    influencers: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


# ============================================
# APPLICATION FASTAPI
# ============================================

app = FastAPI(
    title="TikTok Analysis API",
    description="API pour transcrire, traduire, détecter l'IA et trouver des influenceurs TikTok",
    version="1.0.0"
)

# CORS pour autoriser le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # À restreindre en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Stockage temporaire des résultats (à remplacer par Redis/DB en production)
analysis_storage: Dict[str, Dict[str, Any]] = {}


# ============================================
# FONCTIONS UTILITAIRES
# ============================================

def run_actor_sync(actor_id: str, input_data: Dict) -> Optional[List]:
    """Exécute un actor Apify de manière synchrone"""
    try:
        # Démarrer l'actor
        url = f"https://api.apify.com/v2/acts/{actor_id}/runs?token={API_KEY}"
        response = requests.post(url, json=input_data)
        
        if response.status_code != 201:
            return None
        
        run_data = response.json()
        run_id = run_data['data']['id']
        
        # Attendre la fin
        while True:
            status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={API_KEY}"
            status_response = requests.get(status_url)
            status_data = status_response.json()
            status = status_data['data']['status']
            
            if status in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                break
            
            time.sleep(2)
        
        if status != 'SUCCEEDED':
            return None
        
        # Récupérer les résultats
        dataset_url = f"https://api.apify.com/v2/actor-runs/{run_id}/dataset/items?token={API_KEY}&format=json"
        dataset_response = requests.get(dataset_url)
        
        if dataset_response.status_code != 200:
            return None
        
        return dataset_response.json()
    
    except Exception as e:
        print(f"Erreur dans run_actor_sync: {e}")
        return None


async def run_actor_async(actor_id: str, input_data: Dict) -> Optional[List]:
    """Version asynchrone de run_actor_sync"""
    return await asyncio.get_event_loop().run_in_executor(
        None, run_actor_sync, actor_id, input_data
    )


# ============================================
# ENDPOINTS DE L'API
# ============================================

@app.get("/")
async def root():
    """Endpoint racine"""
    return {
        "name": "TikTok Analysis API",
        "version": "1.0.0",
        "endpoints": {
            "POST /analyze": "Analyser une vidéo TikTok (asynchrone)",
            "GET /analyze/{run_id}": "Récupérer les résultats d'une analyse",
            "GET /languages": "Lister les langues disponibles",
            "GET /health": "Vérifier l'état de l'API"
        }
    }


@app.get("/health")
async def health():
    """Vérification de santé de l'API"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/languages")
async def get_languages():
    """Liste toutes les langues disponibles pour la traduction"""
    return {"languages": AVAILABLE_LANGUAGES}


@app.post("/analyze", response_model=AnalysisStatusResponse)
async def analyze_video(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    Lance l'analyse d'une vidéo TikTok
    Retourne immédiatement un run_id pour suivre la progression
    """
    # Valider les langues
    request.validate_languages()
    
    # Générer un ID unique pour cette analyse
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    
    # Stocker l'état initial
    analysis_storage[run_id] = {
        "run_id": run_id,
        "tiktok_url": request.tiktok_url,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "request": request.dict()
    }
    
    # Ajouter la tâche en arrière-plan
    background_tasks.add_task(
        process_analysis,
        run_id,
        request
    )
    
    return AnalysisStatusResponse(
        run_id=run_id,
        status="pending",
        created_at=analysis_storage[run_id]["created_at"],
        result_url=f"/analyze/{run_id}"
    )


@app.get("/analyze/{run_id}", response_model=AnalysisResultResponse)
async def get_analysis_result(run_id: str):
    """Récupère les résultats d'une analyse complétée"""
    
    if run_id not in analysis_storage:
        raise HTTPException(status_code=404, detail="Analyse non trouvée")
    
    data = analysis_storage[run_id]
    
    return AnalysisResultResponse(
        run_id=data["run_id"],
        tiktok_url=data["tiktok_url"],
        status=data["status"],
        transcript=data.get("transcript"),
        ai_score=data.get("ai_score"),
        ai_is_ai_generated=data.get("ai_is_ai_generated"),
        translations=data.get("translations"),
        influencers=data.get("influencers"),
        error=data.get("error"),
        created_at=data["created_at"],
        completed_at=data.get("completed_at")
    )


# ============================================
# TRAITEMENT EN ARRIÈRE-PLAN
# ============================================

async def process_analysis(run_id: str, request: AnalyzeRequest):
    """
    Traite l'analyse complète en arrière-plan
    """
    try:
        # Mettre à jour le statut
        analysis_storage[run_id]["status"] = "processing"
        
        results = {}
        
        # ========================================
        # ÉTAPE 1: Transcription TikTok
        # ========================================
        analysis_storage[run_id]["current_step"] = "transcription"
        
        transcript_result = await run_actor_async(
            ACTORS["transcriber"],
            {
                "videoUrls": [request.tiktok_url],
                "translationLanguages": ["fr", "en"],
                "includeOriginal": True
            }
        )
        
        if not transcript_result:
            raise Exception("Échec de la transcription TikTok")
        
        original_text = transcript_result[0].get('transcript', transcript_result[0].get('text', ''))
        results["transcript"] = original_text
        analysis_storage[run_id]["transcript"] = original_text
        
        # ========================================
        # ÉTAPE 2: Traduction (optionnelle)
        # ========================================
        if request.translate and original_text:
            analysis_storage[run_id]["current_step"] = "translation"
            translations = {}
            
            for lang in request.target_languages[:10]:  # Limite de 10 pour la démo
                translation_result = await run_actor_async(
                    ACTORS["deepl"],
                    {
                        "text": original_text[:3000],  # Limite de caractères
                        "targetLang": lang,
                        "sourceLang": "EN"
                    }
                )
                
                if translation_result and len(translation_result) > 0:
                    translated = translation_result[0].get('text', translation_result[0].get('translations', ''))
                    translations[lang] = translated
            
            results["translations"] = translations
            analysis_storage[run_id]["translations"] = translations
        
        # ========================================
        # ÉTAPE 3: Détection IA (optionnelle)
        # ========================================
        if request.detect_ai and original_text:
            analysis_storage[run_id]["current_step"] = "ai_detection"
            
            ai_result = await run_actor_async(
                ACTORS["ai_detector"],
                {"text": original_text[:5000]}  # Limite de caractères
            )
            
            if ai_result and len(ai_result) > 0:
                ai_score = ai_result[0].get('score', ai_result[0].get('probability', 0))
                results["ai_score"] = ai_score
                results["ai_is_ai_generated"] = ai_score > 0.5 if isinstance(ai_score, (int, float)) else None
                analysis_storage[run_id]["ai_score"] = ai_score
                analysis_storage[run_id]["ai_is_ai_generated"] = results["ai_is_ai_generated"]
        
        # ========================================
        # ÉTAPE 4: Recherche d'influenceurs (optionnelle)
        # ========================================
        if request.find_influencers:
            analysis_storage[run_id]["current_step"] = "influencer_search"
            
            brand_desc = request.brand_description or "Marque dynamique cherchant des influenceurs"
            
            influencer_result = await run_actor_async(
                ACTORS["influencer_finder"],
                {
                    "brandDescription": brand_desc,
                    "targetAudience": "Jeunes adultes actifs sur TikTok",
                    "maxResults": request.max_influencers
                }
            )
            
            if influencer_result:
                results["influencers"] = influencer_result
                analysis_storage[run_id]["influencers"] = influencer_result
        
        # ========================================
        # FINALISATION
        # ========================================
        analysis_storage[run_id]["status"] = "completed"
        analysis_storage[run_id]["completed_at"] = datetime.now().isoformat()
        analysis_storage[run_id]["results"] = results
        
        print(f"✅ Analyse {run_id} terminée avec succès")
    
    except Exception as e:
        print(f"❌ Erreur lors de l'analyse {run_id}: {str(e)}")
        analysis_storage[run_id]["status"] = "failed"
        analysis_storage[run_id]["error"] = str(e)
        analysis_storage[run_id]["completed_at"] = datetime.now().isoformat()


# ============================================
# POINT D'ENTRÉE
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
