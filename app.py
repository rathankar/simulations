# app.py
import streamlit as st, json, pandas as pd, requests, time, textwrap

# ----------  STATIC CATALOGUES ------------------------------------------------
with open("ophysics.json") as f:
    OPHY = json.load(f)
with open("phet.json") as f:
    PHET = json.load(f)

CAT = {"oPhysics": OPHY, "PhET": PHET}

# ----------  GEMINI WRAPPER ---------------------------------------------------
def gemini(api_key: str, prompt: str) -> str:
    url = ("https://generativelanguage.googleapis.com/v1/models/"
           "gemini-2.5-flash:generateContent?key="+api_key)
    payload = {"contents":[{"parts":[{"text":prompt}]}]}
    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

# ----------  PAGE CONFIG ------------------------------------------------------
st.set_page_config(page_title="Mechanics Lab", page_icon="🧪", layout="wide")
if "stage" not in st.session_state:   # 0 = login … 5 = feedback
    st.session_state.stage = 0
if "data"  not in st.session_state:   # raw table, list-of-lists
    st.session_state.data = []
if "Q"     not in st.session_state:   # 10 questions
    st.session_state.Q = []
if "A"     not in st.session_state:   # answers
    st.session_state.A = []

# ----------  STAGE 0  LOGIN ---------------------------------------------------
if st.session_state.stage == 0:
    st.header("Student login")
    name = st.text_input("Name")
    clas = st.text_input("Class")
    api  = st.text_input("Gemini API key", type="password")
    if st.button("Login"):
        if not (name and clas and api):
            st.warning("Fill every field")
        else:
            st.session_state.name  = name
            st.session_state.class_ = clas
            st.session_state.key   = api
            st.session_state.stage = 1
            st.rerun()

# ----------  STAGE 1  SIM PICKER ---------------------------------------------
if st.session_state.stage == 1:
    st.header("Choose a simulation")
    plat = st.selectbox("Platform", [""]+list(CAT.keys()))
    if plat:
        sim_names = [s["n"] for s in CAT[plat]]
        idx = st.selectbox("Simulation", range(len(sim_names)), format_func=lambda i: sim_names[i])
        sim = CAT[plat][idx]
        st.markdown(f"**{sim['n']}**  \n{sim['i']}  \n[Open simulation]({sim['u']})")
        ind = st.selectbox("Independent variable",
                           sim["v"] if sim["v"] else ["(type your own)"])
        if ind == "(type your own)":
            ind = st.text_input("Independent variable")
        dep = st.selectbox("Dependent variable",
                           sim["m"] if sim["m"] else ["(type your own)"])
        if dep == "(type your own)":
            dep = st.text_input("Dependent variable")
        if st.button("Proceed →") and ind and dep:
            st.session_state.sim = sim
            st.session_state.ind = ind
            st.session_state.dep = dep
            # blank 5×4 table
            st.session_state.data = [[None,None,None,None] for _ in range(5)]
            st.session_state.stage = 2
            st.experimental_rerun()

# ----------  STAGE 2  DATA ENTRY ---------------------------------------------
if st.session_state.stage == 2:
    st.header(st.session_state.sim["n"])
    st.subheader(f"vary **{st.session_state.ind}**, measure **{st.session_state.dep}**")
    cols = [st.session_state.ind, "Trial 1", "Trial 2", "Trial 3"]
    df = pd.DataFrame(st.session_state.data, columns=cols)
    edited = st.data_editor(df, num_rows="fixed", key="table")
    if st.button("Submit data"):
        if edited.isna().any().any():
            st.warning("Fill every cell")
        else:
            st.session_state.data = edited.astype(str).values.tolist()
            st.session_state.stage = 3
            st.experimental_rerun()

# ----------  STAGE 3  GET QUESTIONS FROM GEMINI ------------------------------
if st.session_state.stage == 3:
    st.info("Generating questions… please wait ≈ 15 s")
    raw = "\n".join(",".join(r) for r in st.session_state.data)
    prompt = textwrap.dedent(f"""
      You are an IB DP Physics teacher (2025 syllabus).
      Simulation: {st.session_state.sim['n']}
      URL: {st.session_state.sim['u']}
      Independent variable: {st.session_state.ind}
      Dependent variable: {st.session_state.dep}
      Raw data table:
      {raw}

      Write EXACTLY 10 numbered questions that rely exclusively on this simulation and data.
      Cover IA strands: hypothesis, variables, trend, outliers, uncertainty, evaluation, conclusion etc.
      Plain English, no LaTeX.
    """).strip()
    try:
        qtxt = gemini(st.session_state.key, prompt)
        st.session_state.Q = [q.lstrip("0123456789. )") for q in qtxt.split("\n") if q and q[0].isdigit()]
        if len(st.session_state.Q)!=10: raise ValueError("Gemini returned wrong count")
        st.session_state.A = []
        st.session_state.stage = 4
        st.experimental_rerun()
    except Exception as e:
        st.error(f"Gemini error: {e}")

# ----------  STAGE 4  Q-&-A LOOP ---------------------------------------------
if st.session_state.stage == 4:
    i = len(st.session_state.A)
    st.markdown(miniTable := pd.DataFrame(st.session_state.data,
                         columns=[st.session_state.ind,"1","2","3"]).to_html(index=False),
                unsafe_allow_html=True)
    st.subheader(f"Question {i+1} / 10")
    st.write(st.session_state.Q[i])
    ans = st.text_area("Your answer", key=f"ans_{i}")
    col1,col2 = st.columns(2)
    if col1.button("Submit"):
        if not ans.strip(): st.warning("Type something")
        else:
            st.session_state.A.append(ans.strip())
            if len(st.session_state.A)==10:
                st.session_state.stage = 5
            st.experimental_rerun()
    if col2.button("Quit"): st.stop()

# ----------  STAGE 5  GRADING -------------------------------------------------
if st.session_state.stage == 5:
    st.info("Grading… please wait ≈ 15 s")
    bundle = "\n".join(f"Q{i+1}: {q}\nA{i+1}: {a}"
                       for i,(q,a) in enumerate(zip(st.session_state.Q, st.session_state.A)))
    prompt = textwrap.dedent(f"""
      Grade each answer 0-5 and give a correct answer & short reason.
      Return JSON: {{
        "grades":[10], "correct":[10], "reasons":[10], "overall":""
      }}
      {bundle}
    """)
    try:
        res = gemini(st.session_state.key, prompt)
        data = json.loads(res[res.find("{"): res.rfind("}")+1])
    except Exception as e:
        st.error(f"Gemini / JSON error: {e}")
        st.stop()

    st.header("Feedback & grading")
    for i,q in enumerate(st.session_state.Q):
        st.markdown(f"**{i+1}. {q}** &nbsp; <span class='score'>{data['grades'][i]}/5</span>",
                    unsafe_allow_html=True)
        st.write("Your answer:", st.session_state.A[i])
        st.write("Model answer:", data["correct"][i])
        st.caption(data["reasons"][i])
        st.divider()
    st.subheader("Overall comment")
    st.write(data["overall"])
    if st.button("🔄 Restart"):
        for k in ("stage","data","Q","A"): st.session_state.pop(k, None)
        st.experimental_rerun()
