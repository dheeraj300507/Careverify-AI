import os
import uuid
import datetime
from app.services.supabase_client import get_supabase_admin

def seed_demo_claims():
    supabase = get_supabase_admin()
    
    # 1. Ensure a Hospital Org exists
    hospital_name = "General Hospital East"
    existing_hosp = supabase.table("organizations").select("*").eq("name", hospital_name).execute()
    if not existing_hosp.data:
        hosp_record = {
            "name": hospital_name,
            "type": "hospital",
            "trust_score": 82.5,
            "is_active": True
        }
        hosp = supabase.table("organizations").insert(hosp_record).execute().data[0]
        print(f"Created Hospital: {hosp['id']}")
        hosp_id = hosp['id']
    else:
        hosp_id = existing_hosp.data[0]['id']
        print(f"Using Existing Hospital: {hosp_id}")

    # 2. Ensure an Insurance Org exists
    insurer_name = "BlueShield Metro"
    existing_ins = supabase.table("organizations").select("*").eq("name", insurer_name).execute()
    if not existing_ins.data:
        ins_record = {
            "name": insurer_name,
            "type": "insurance",
            "trust_score": 95.0,
            "is_active": True
        }
        ins = supabase.table("organizations").insert(ins_record).execute().data[0]
        print(f"Created Insurer: {ins['id']}")
        ins_id = ins['id']
    else:
        ins_id = existing_ins.data[0]['id']
        print(f"Using Existing Insurer: {ins_id}")

    # 3. Seed Claim CLM-99214 (Orthopedics)
    claim_id_99214 = "99214000-0000-0000-0000-000000000000" # Static UUID for easy mapping
    existing_claim = supabase.table("claims").select("id").eq("id", claim_id_99214).execute()
    
    claim_data = {
        "id": claim_id_99214,
        "claim_number": "CLM-99214",
        "hospital_org_id": hosp_id,
        "insurance_org_id": ins_id,
        "claimed_amount": 18450.00,
        "status": "pending_review",
        "priority": 4,
        "trust_score": 35.0, # Low trust to trigger "High Risk" UI
        "fraud_probability": 0.82,
        "diagnosis_codes": ["M17.11"],
        "procedure_codes": ["27447"],
        "admission_date": (datetime.datetime.now() - datetime.timedelta(days=5)).date().isoformat(),
        "discharge_date": (datetime.datetime.now() - datetime.timedelta(days=2)).date().isoformat(),
        "ai_recommendation": "COMPLIANCE_REVIEW_REQUIRED",
        "ai_explanation": {
            "explanation_text": "CareVerify Trust Score: 35/100. Potential duplicate detected for CPT 27447.",
            "risk_factors": [
                {"severity": "high", "factor": "Potential duplicate CPT detected", "impact": -30},
                {"severity": "medium", "factor": "High amount relative to similar cases", "impact": -15}
            ]
        }
    }
    
    if not existing_claim.data:
        supabase.table("claims").insert(claim_data).execute()
        print(f"Seeded Claim: CLM-99214")
    else:
        supabase.table("claims").update(claim_data).eq("id", claim_id_99214).execute()
        print(f"Updated Claim: CLM-99214")

if __name__ == "__main__":
    # Mock environment for standalone script
    os.environ.setdefault("SUPABASE_URL", "https://xyz.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "xyz")
    
    # In reality, the wsgi.py env will be used. 
    # Let's try running it within the app context or just importing settings.
    try:
        from config.settings import config_map
        config = config_map["development"]
        os.environ["SUPABASE_URL"] = config.SUPABASE_URL
        os.environ["SUPABASE_SERVICE_KEY"] = config.SUPABASE_SERVICE_KEY
        seed_demo_claims()
    except Exception as e:
        print(f"Error seeding: {e}")
