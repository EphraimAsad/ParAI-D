import pandas as pd

class ParasiteIdentifier:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    @staticmethod
    def _split_vals(v):
        return [s.strip().lower() for s in str(v).split(";") if s.strip()]

    def _match_any(self, user_vals, db_vals):
        user_vals = [u.lower() for u in user_vals]
        db_vals = [d.lower() for d in db_vals]
        return any(u in db_vals for u in user_vals)

    def score_entry(self, user_input: dict):
        results = []
        for _, row in self.df.iterrows():
            score = 0
            max_score = 113  # normalization baseline

            def get_list(field):
                return self._split_vals(row.get(field, ""))

            # Countries (5)
            if self._match_any(user_input.get("Countries Visited", []), get_list("Countries Visited")):
                score += 5
            # Anatomy (5)
            if self._match_any(user_input.get("Anatomy Involvement", []), get_list("Anatomy Involvement")):
                score += 5
            # Vector (8) with special 'Other(Including Unknown)' rule
            vec_list = [x.lower() for x in user_input.get("Vector Exposure", [])]
            if vec_list == ["other(including unknown)"]:
                score += 8
            elif self._match_any(user_input.get("Vector Exposure", []), get_list("Vector Exposure")):
                score += 8
            # Symptoms (10) proportional
            ui_sy = user_input.get("Symptoms", [])
            if ui_sy and ui_sy != ["Unknown"]:
                db_sy = get_list("Symptoms")
                matches = sum(1 for s in ui_sy if s.lower() in db_sy)
                score += (10 / len(ui_sy)) * matches
            # Duration (5)
            if self._match_any(user_input.get("Duration of Illness", []), get_list("Duration of Illness")):
                score += 5
            # Animal contact (8)
            if self._match_any(user_input.get("Animal Contact Type", []), get_list("Animal Contact Type")):
                score += 8
            # Blood film (15): negative mismatch = -10; any positive pattern = +15
            u_bf = [x.lower() for x in user_input.get("Blood Film Result", [])][0]
            db_bf = get_list("Blood Film Result")
            if u_bf != "unknown":
                if u_bf == "negative":
                    if "negative" not in db_bf:
                        score -= 10
                else:
                    if any(x != "negative" for x in db_bf):
                        score += 15
            # Immune status (2)
            if self._match_any(user_input.get("Immune Status", []), get_list("Immune Status")):
                score += 2
            # LFT (5) with 'Variable' rule
            db_lft = get_list("Liver Function Tests")
            u_lft = [x.lower() for x in user_input.get("Liver Function Tests", [])][0]
            if "variable" in db_lft or u_lft in db_lft:
                score += 5
            # Binary markers (5 each) with Variable rule
            for f in [
                "Neurological Involvement", "Eosinophilia", "Fever",
                "Diarrhea", "Bloody Diarrhea", "Stool Cysts or Ova",
                "Anemia", "High IgE Level"
            ]:
                db = get_list(f)
                u = [x.lower() for x in user_input.get(f, [])][0]
                if u != "unknown" and ("variable" in db or u in db):
                    score += 5
            # Cysts on Imaging (10): negative mismatch = -5; any non-negative pattern = +10
            db_c = get_list("Cysts on Imaging")
            u_c = [x.lower() for x in user_input.get("Cysts on Imaging", [])][0]
            if u_c != "unknown":
                if u_c == "negative" and "negative" not in db_c:
                    score -= 5
                elif any(x != "negative" for x in db_c):
                    score += 10

            results.append({
                "Parasite": row.get("Parasite"),
                "Group": row.get("Group"),
                "Subtype": row.get("Subtype"),
                "Score": score,
                "Likelihood (%)": round((score / max_score) * 100, 2),
                "Key Test": row.get("Key Test", row.get("Key test", row.get("Key Notes", ""))),
            })
        return pd.DataFrame(results).sort_values("Likelihood (%)", ascending=False).reset_index(drop=True)
