import pandas as pd

SENTINEL = "__unset__"  # do not score or consider when present

class ParasiteIdentifier:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    @staticmethod
    def _split_vals(v):
        return [s.strip().lower() for s in str(v).split(";") if s and s.strip()]

    def _match_any(self, user_vals, db_vals):
        u = [x.lower() for x in user_vals if str(x).strip()]
        d = [x.lower() for x in db_vals if str(x).strip()]
        return any(x in d for x in u)

    @staticmethod
    def _valid_user(val):
        """True only if user provided a meaningful value (not empty, not Unknown, not sentinel)."""
        if not val:
            return False
        if isinstance(val, list):
            vals = [str(x).lower() for x in val if str(x).strip()]
            return any(x not in ("unknown", "choose…", "choose...", SENTINEL, "") for x in vals)
        v = str(val).lower()
        return v not in ("unknown", "choose…", "choose...", SENTINEL, "")

    def score_entry(self, user_input: dict):
        results = []
        for _, row in self.df.iterrows():
            score = 0
            max_score = 113  # normalization baseline (your weights)

            def get_list(field):
                return self._split_vals(row.get(field, ""))

            # Countries (5)
            if self._valid_user(user_input.get("Countries Visited", [])) and \
               self._match_any(user_input.get("Countries Visited", []), get_list("Countries Visited")):
                score += 5

            # Anatomy (5)
            if self._valid_user(user_input.get("Anatomy Involvement", [])) and \
               self._match_any(user_input.get("Anatomy Involvement", []), get_list("Anatomy Involvement")):
                score += 5

            # Vector (8) + special rule
            if self._valid_user(user_input.get("Vector Exposure", [])):
                vec_list = [x.lower() for x in user_input.get("Vector Exposure", [])]
                if vec_list == ["other(including unknown)"]:
                    score += 8
                elif self._match_any(user_input.get("Vector Exposure", []), get_list("Vector Exposure")):
                    score += 8

            # Symptoms (10) proportional
            ui_sy = user_input.get("Symptoms", [])
            if self._valid_user(ui_sy):
                db_sy = get_list("Symptoms")
                matches = sum(1 for s in ui_sy if str(s).lower() in db_sy)
                score += (10 / max(1, len(ui_sy))) * matches

            # Duration (5)
            if self._valid_user(user_input.get("Duration of Illness", [])) and \
               self._match_any(user_input.get("Duration of Illness", []), get_list("Duration of Illness")):
                score += 5

            # Animal contact (8)
            if self._valid_user(user_input.get("Animal Contact Type", [])) and \
               self._match_any(user_input.get("Animal Contact Type", []), get_list("Animal Contact Type")):
                score += 8

            # Blood Film (15): Unknown/Choose ignored; negative mismatch = -10; any positive pattern = +15
            u_bf = [str(x).lower() for x in user_input.get("Blood Film Result", [])][:1] or [SENTINEL]
            db_bf = get_list("Blood Film Result")
            if self._valid_user(u_bf):
                bf = u_bf[0]
                if bf == "negative":
                    if all(x != "negative" for x in db_bf):
                        score -= 10
                else:
                    if any(x != "negative" for x in db_bf):
                        score += 15

            # Immune status (2)
            if self._valid_user(user_input.get("Immune Status", [])) and \
               self._match_any(user_input.get("Immune Status", []), get_list("Immune Status")):
                score += 2

            # LFT (5) with 'Variable' rule; Unknown/Choose ignored
            db_lft = get_list("Liver Function Tests")
            u_lft = [str(x).lower() for x in user_input.get("Liver Function Tests", [])][:1] or [SENTINEL]
            if self._valid_user(u_lft):
                if "variable" in db_lft or u_lft[0] in db_lft:
                    score += 5

            # Binary fields (5 each) with Variable rule; Unknown/Choose ignored
            for f in [
                "Neurological Involvement", "Eosinophilia", "Fever",
                "Diarrhea", "Bloody Diarrhea", "Stool Cysts or Ova",
                "Anemia", "High IgE Level"
            ]:
                u = [str(x).lower() for x in user_input.get(f, [])][:1] or [SENTINEL]
                db = get_list(f)
                if self._valid_user(u) and ("variable" in db or u[0] in db):
                    score += 5

            # Cysts on Imaging (10): Unknown/Choose ignored; negative mismatch = -5; any non-negative pattern = +10
            db_c = get_list("Cysts on Imaging")
            u_c = [str(x).lower() for x in user_input.get("Cysts on Imaging", [])][:1] or [SENTINEL]
            if self._valid_user(u_c):
                cval = u_c[0]
                if cval == "negative":
                    if all(x != "negative" for x in db_c):
                        score -= 5
                else:
                    if any(x != "negative" for x in db_c):
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
