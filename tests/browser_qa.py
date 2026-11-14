"""Optional browser QA. Requires a local server, Chrome CDP on 9227 and websockets."""
import os
import base64
import json
import time
import urllib.request
from pathlib import Path
from uuid import uuid4
from websockets.sync.client import connect
from app.db import SessionLocal
from app.models import User, Patient, Visit, Appointment, MedicalOrder
from app.core.config import settings
from app.services.medical_images import private_path
from tests.test_medical_orders import photo_bytes

base_url=os.environ.get("QA_BASE_URL", "http://127.0.0.1:8000")

email=f"browser-{uuid4().hex}@example.com"
seq=0
errors=[]
tabs=json.load(urllib.request.urlopen("http://127.0.0.1:9227/json"))
ws=connect(next(tab for tab in tabs if tab["type"] == "page")["webSocketDebuggerUrl"])
def command(method,params=None):
    global seq
    seq+=1
    ws.send(json.dumps({"id":seq,"method":method,"params":params or {}}))
    while True:
        message=json.loads(ws.recv(timeout=30))
        if message.get("method")=="Runtime.exceptionThrown": errors.append(message["params"])
        if message.get("id")==seq:
            if "error" in message: raise AssertionError(message["error"])
            return message.get("result",{})
def js(expression):
    result=command("Runtime.evaluate",{"expression":expression,"returnByValue":True,"awaitPromise":True})
    if "exceptionDetails" in result:raise AssertionError(result["exceptionDetails"])
    return result.get("result",{}).get("value")
def wait(expression):
    deadline=time.time()+20
    while time.time()<deadline:
        if js(expression):return
        time.sleep(.2)
    raise AssertionError(f"Timed out: {expression}; editor error: {js('document.querySelector("#editor-error")?.textContent')}; auth error: {js('document.querySelector("#auth-error")?.textContent')}")
def fill(selector,values):
    js(f"(()=>{{const f=document.querySelector({json.dumps(selector)});for(const [k,v] of Object.entries({json.dumps(values)})){{const el=f.elements[k];el.value=v;el.dispatchEvent(new Event('input',{{bubbles:true}}));}}f.requestSubmit();}})()")
def screenshot(name):
    Path('artifacts').mkdir(exist_ok=True)
    command('Page.bringToFront')
    data=command('Page.captureScreenshot',{'format':'png','captureBeyondViewport':True,'clip':{'x':0,'y':0,'width':js('innerWidth'),'height':js('document.documentElement.scrollHeight'),'scale':1}})
    Path(f'artifacts/{name}.png').write_bytes(base64.b64decode(data['data']))
try:
    command('Runtime.enable');command('Page.enable')
    command('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
    command('Page.navigate',{'url':base_url+'/'})
    wait('document.querySelector(".closing") !== null')
    screenshot('landing-desktop')
    command('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
    assert js('document.documentElement.scrollWidth <= innerWidth'), 'Landing overflows mobile'
    assert js('document.querySelector(".login-link").getBoundingClientRect().width > 0'), 'Mobile login link is hidden'
    screenshot('landing-mobile')
    command('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
    command('Page.navigate',{'url':base_url+'/registro'})
    wait('document.querySelector("#auth-screen") && !document.querySelector("#auth-screen").classList.contains("hidden")')
    fill('#auth-form',{'full_name':'Profesional QA','specialty':'Kinesiología','email':email,'password':'BrowserOnly!12345'})
    wait('document.querySelector("#app-screen") && !document.querySelector("#app-screen").classList.contains("hidden")')
    wait('document.querySelector("#recent-patients").textContent.includes("Todavía")')
    screenshot('portal-desktop')
    js('document.querySelector("[data-action=new-patient]").click()')
    wait('document.querySelector("#editor").open')
    fill('#editor-form',{'first_names':'Paciente Browser','last_names':'Prueba','rut':'12345678-1','age':'34','first_visit_date':'2026-11-12','pre_existing_conditions':'Sin antecedentes conocidos'})
    wait('document.querySelector("#editor-error").textContent.length > 0')
    fill('#editor-form',{'rut':'12345678-5'})
    wait('!document.querySelector("#editor").open')
    wait('document.querySelector("#record-header").textContent.includes("Paciente Browser")')
    js('document.querySelector("#new-visit").click()')
    assert js('document.querySelectorAll("#editor-fields textarea").length === 4'), 'Visit form must have four text areas'
    assert js('document.querySelectorAll("#editor-fields textarea[required]").length === 1'), 'Only history/evolution is required'
    assert js('!document.querySelector(".visit-additional").open'), 'Additional fields should start collapsed'
    assert js('document.querySelector("#editor-form button[type=submit]").textContent === "Guardar atención"')
    command('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
    js('document.querySelector("#editor-fields [name=new_findings]").value=("Texto de prueba"+String.fromCharCode(10)).repeat(16);document.querySelector("#editor-fields [name=new_findings]").dispatchEvent(new Event("input",{bubbles:true}))')
    assert js('document.querySelector("#editor-fields [name=new_findings]").offsetHeight > 200'), 'Visit text area does not grow'
    assert js('document.documentElement.scrollWidth <= innerWidth'), 'Visit form overflows mobile'
    screenshot('visit-four-fields-mobile')
    js('document.querySelector(".visit-additional summary").click()')
    fill('#editor-form',{'visit_date':'2026-11-12','new_findings':'Buena evolución clínica','treatment_plan':'Seguimiento semanal','pain_scale':'0'})
    wait('!document.querySelector("#editor").open')
    wait('document.querySelector("#visit-list").textContent.includes("Buena evolución")')
    screenshot('clinical-record')
    legacy_payload={'patient_id':js('state.patient.id'),'visit_date':'2026-11-11','chief_complaint':'Motivo anterior <b>sin HTML</b>','objective_exam':'Examen anterior','new_findings':'Evolución anterior','clinical_assessment':'Valoración anterior','treatment_plan':'Tratamiento anterior','home_exercises':'Ejercicio anterior','recommendations':'Cuidado anterior','pain_scale':0,'next_visit_date':'2026-11-20'}
    legacy=js(f'api("/api/visits",{{method:"POST",body:JSON.stringify({json.dumps(legacy_payload)})}})')
    js('openRecord(state.patient.id)')
    wait('document.querySelector("#visit-list").textContent.includes("Valoración anterior")')
    assert js('!document.querySelector("#visit-list b")'), 'Legacy text was interpreted as HTML'
    js(f'editVisit(state.visits.find(v=>v.id==={legacy["id"]}))')
    wait('document.querySelector("#editor").open')
    assert js('document.querySelectorAll("#editor-fields textarea").length === 4')
    assert js('document.querySelector(".visit-legacy-note") !== null')
    assert js('document.querySelector(".visit-additional").open'), 'Existing zero pain/follow-up must remain visible'
    merged=js('document.querySelector("#editor-fields [name=new_findings]").value')
    instructions=js('document.querySelector("#editor-fields [name=home_exercises]").value')
    assert all(legacy_payload[key] in merged for key in ['chief_complaint','new_findings','clinical_assessment'])
    assert all(legacy_payload[key] in instructions for key in ['home_exercises','recommendations'])
    fill('#editor-form',{})
    wait('!document.querySelector("#editor").open')
    wait('document.querySelector("#visit-list").textContent.includes("Valoración anterior")')
    saved=js(f'api("/api/visits/patient/{legacy_payload["patient_id"]}").then(rows=>rows.find(v=>v.id==={legacy["id"]}))')
    assert saved['new_findings']==merged and saved['home_exercises']==instructions
    assert saved['chief_complaint'] is None and saved['clinical_assessment'] is None and saved['recommendations'] is None
    assert saved['objective_exam']==legacy_payload['objective_exam'] and saved['treatment_plan']==legacy_payload['treatment_plan']
    assert saved['pain_scale']==0 and saved['next_visit_date']==legacy_payload['next_visit_date']
    js(f'editVisit(state.visits.find(v=>v.id==={legacy["id"]}))')
    assert js('document.querySelector("#editor-fields [name=new_findings]").value')==merged, 'Legacy content duplicated on second edit'
    fill('#editor-form',{})
    wait('!document.querySelector("#editor").open')
    fixture=Path('artifacts/qa-order.jpg');fixture.write_bytes(photo_bytes())
    js('document.querySelector("#add-medical-order").click()')
    wait('document.querySelector("#order-upload-dialog").open')
    assert js('document.querySelector("#order-camera").getAttribute("capture") === "environment"')
    command('DOM.enable')
    root=command('DOM.getDocument')['root']['nodeId']
    file_node=command('DOM.querySelector',{'nodeId':root,'selector':'#order-gallery'})['nodeId']
    command('DOM.setFileInputFiles',{'nodeId':file_node,'files':[str(fixture.resolve())]})
    wait('document.querySelector("#order-preview-image").naturalWidth > 0')
    fill('#order-upload-form',{'title':'Orden médica de prueba','document_date':'2026-11-12','notes':'Documento temporal de prueba'})
    wait('!document.querySelector("#order-upload-dialog").open')
    wait('document.querySelector("#medical-orders-list").textContent.includes("Orden médica de prueba")')
    js('document.querySelector("[data-order-view]").click()')
    wait('document.querySelector("#order-view-dialog").open && document.querySelector("#order-view-image").naturalWidth > 0')
    command('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
    assert js('document.documentElement.scrollWidth <= innerWidth'), 'Document viewer overflows mobile'
    screenshot('medical-order-mobile')
    js('document.querySelector("#delete-medical-order").click()')
    js('document.querySelector("#confirm-delete-order").click()')
    wait('!document.querySelector("#order-view-dialog").open')
    wait('!document.querySelector("#medical-orders-list").textContent.includes("Orden médica de prueba")')
    command('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
    js('document.querySelector("[data-action=patient-appointment]").click()')
    fill('#editor-form',{'starts_at':js('state.day')+'T11:00','ends_at':js('state.day')+'T11:45','reason':'Control de seguimiento'})
    wait('!document.querySelector("#editor").open')
    js('document.querySelector("#app-nav [data-view=agenda]").click()')
    wait('document.querySelector("#agenda-events").textContent.includes("Control de seguimiento")')
    screenshot('agenda-desktop')
    js('document.querySelector("[data-action=edit-appointment]").click()')
    fill('#editor-form',{'status':'cancelled'})
    wait('!document.querySelector("#editor").open')
    wait('document.querySelector("#agenda-events").textContent.includes("Cancelada")')
    command('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
    assert js('document.documentElement.scrollWidth <= innerWidth'), 'Portal overflows mobile'
    screenshot('portal-mobile')
    js('document.querySelector("#app-nav [data-view=profile]").click()')
    wait('!document.querySelector("#view-profile").classList.contains("hidden")')
    fill('#profile-form',{'full_name':'Profesional QA Actualizado','specialty':'Piso Pélvico','phone':'+56912345678','appointment_minutes':'60','work_start':'08:30','work_end':'18:00'})
    wait('document.querySelector("#user-name").textContent.includes("Actualizado")')
    fill('#password-form',{'current_password':'BrowserOnly!12345','new_password':'BrowserUpdated!12345','confirm_password':'MismatchOnly!12345'})
    wait('document.querySelector("#password-form .form-message").textContent.includes("no coinciden")')
    fill('#password-form',{'current_password':'WrongOnly!12345','new_password':'BrowserUpdated!12345','confirm_password':'BrowserUpdated!12345'})
    wait('document.querySelector("#password-form .form-message").textContent.includes("actual es incorrecta")')
    js('document.querySelector("[data-password-target=password-new]").click()')
    assert js('document.querySelector("#password-new").type === "text"')
    fill('#password-form',{'current_password':'BrowserOnly!12345','new_password':'BrowserUpdated!12345','confirm_password':'BrowserUpdated!12345'})
    wait('document.querySelector("#password-status").textContent.includes("actualizada correctamente")')
    assert js('document.querySelector("#password-new").value === "" && document.querySelector("#password-new").type === "password"')
    assert js('document.documentElement.scrollWidth <= innerWidth'), 'Profile overflows mobile'
    screenshot('profile-mobile')
    command('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
    screenshot('profile-desktop')
    js('document.querySelector("#logout").click()')
    wait('!document.querySelector("#auth-screen").classList.contains("hidden")')
    fill('#auth-form',{'email':email,'password':'BrowserUpdated!12345'})
    wait('!document.querySelector("#app-screen").classList.contains("hidden")')
    js('document.querySelector("#logout").click()')
    wait('!document.querySelector("#auth-screen").classList.contains("hidden")')
    mailbox_path=os.environ.get("QA_MAILBOX_FILE")
    if mailbox_path:
        js('document.querySelector("#forgot-password-link").click()')
        wait('!document.querySelector("#recover-form").classList.contains("hidden")')
        command('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
        fill('#recover-form',{'email':email})
        wait('document.querySelector("#recover-form .form-success").textContent.includes("instrucciones")')
        assert js('document.documentElement.scrollWidth <= innerWidth'), 'Recovery form overflows mobile'
        screenshot('recovery-mobile')
        for _ in range(100):
            if Path(mailbox_path).exists():break
            time.sleep(.1)
        captured=json.loads(Path(mailbox_path).read_text(encoding='utf-8'))
        assert captured['recipient']==email
        command('Page.navigate',{'url':base_url+'/restablecer-contrasena#token='+captured['token']})
        wait('!document.querySelector("#reset-recovery-form").classList.contains("hidden")')
        assert js('location.hash === ""'), 'Reset token remains in URL'
        assert js('document.querySelector("meta[name=referrer]").content === "no-referrer"')
        js('document.querySelector("[data-password-target=recovery-new-password]").click()')
        assert js('document.querySelector("#recovery-new-password").type === "text"')
        fill('#reset-recovery-form',{'new_password':'BrowserRecovered!12345','confirm_password':'MismatchOnly!12345'})
        wait('document.querySelector("#reset-recovery-form .form-message").textContent.includes("no coinciden")')
        screenshot('reset-mobile')
        fill('#reset-recovery-form',{'new_password':'BrowserRecovered!12345','confirm_password':'BrowserRecovered!12345'})
        wait('document.querySelector("#auth-status").textContent.includes("actualizada")')
        fill('#auth-form',{'email':email,'password':'BrowserUpdated!12345'})
        wait('document.querySelector("#auth-error").textContent.includes("incorrectos")')
        fill('#auth-form',{'email':email,'password':'BrowserRecovered!12345'})
        wait('!document.querySelector("#app-screen").classList.contains("hidden")')
        js('document.querySelector("#logout").click()')
        wait('!document.querySelector("#auth-screen").classList.contains("hidden")')
    assert not errors,errors
    print('Browser QA OK: registration, patient validation, clinical record, visits, scheduling, cancellation, logout, password recovery, desktop and mobile.')
finally:
    ws.close()
    with SessionLocal() as db:
        ids=[r.id for r in db.query(User).filter(User.email==email)]
        if ids:
            for order in db.query(MedicalOrder).filter(MedicalOrder.professional_id.in_(ids)):
                for flag in (False,True):private_path(Path(settings.storage_dir)/'medical-orders',order.storage_key,flag).unlink(missing_ok=True)
            for model in (MedicalOrder,Appointment,Visit,Patient):db.query(model).filter(model.professional_id.in_(ids)).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
            db.commit()
