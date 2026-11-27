"""Language-level vocabulary. Contains no patient, village or file names."""
from .textutil import phonetic

# Words that can never be (part of) a person name when seen in running text.
_STOP = """
address mobile uhid dob consultant admission discharge presenting history advice medications
attendant signature aadhaar email gender sex bed ipd claim policy insurance bill amount status
full first last beneficiary next kin nurse sister emergency madam staff caregiver neighbour neighbor
mummy papa meri mera person verified informed contacted spoke seen
saath saathi साथ आए आये श्री श्रीमती निवासी संपर्क पुत्री पुत्र
a about abdomen abdominal above acute admission admit admitted advice after again age aged all also
am amount an and any are area as at attendant attached attachment avoid back bad bed
before bill billing blood body bp breath breathing but by called calls cap care case cases
chart chest chronic claim clinic clinical code complaint complaints complained completed
condition confirmed consent consultant contact continue cough course cream csv daily data
date day days dear dengue department diabetes diabetic diagnosis diet differential discharge
discharged disease district doctor dose down dr drop drops drug duration evening examination
export family father female fever file final follow followup for form forwarded found from
gender general given gm good guardian had has have he headache health her hg high him his history
hospital house husband id if improved in including inform informed injection inj inhaler is it
karo lab labs left lena level list log loose low male management me medical medicine medicines
mg mild min ml mmhg mob mobile month months morning mother mr mrn mrs ms name near neend next
night no nodal normal not note notes now number nursing observation of officer ok old on one
only opd or oral other over oxygen pain pathology patient per phone please plan presented
presenting previous problem procedure protocol pt pulse puffs random rate re received record
records ref referred reg registration relation relative remarks report reported requires result
results review right round routine rx sample sd se serum sex she should sig sir sleep so
stable start stool stools study sugar summary surgery symptoms syp tab tablet taken taking
temp temperature test tests than that the then there they this time to today tomorrow total
town treated treatment type ulti under unit unspecified up urinary urine verify version
visit vitals vomiting ward was water we week weeks weight were what when which while who wife
will with within without wk wks workers worker yes yesterday yr yrs you your
village gram vill tehsil distt dist mohalla near opposite opp behind road street lane nagar
january february march april may june july august september october november december
monday tuesday wednesday thursday friday saturday sunday jan feb mar apr jun jul aug sep sept
oct nov dec male female other unknown pending settled approved rejected primary secondary
ka ki ke ko ne se hai hain tha thi the ho raha rahe rahi gaya gayi gaye aur bhi nahi nahin
kya koi kar karo karein diya liya liye dawai dawa bukhar khansi dard pet sir saans kamzori
chakkar theek aaj kal raat subah shaam din hafte mahine abhi ab pe par mein bola boli bataya
kaha dikhaya aaya aayi laaya laayi lekar aaye utar ja jaa wala wali kam zyada khana pani
control condition time utar gya hua hui unka unki unke inka inki iska uska uski mera meri
sab kuch phir lekin agar jab tak wapas dobara band chal rahi chhutti bharti
है हैं था थी थे को का की के से में पर और भी नहीं बुखार दिन दिनों मरीज़ मरीज रोगी नाम आयु उम्र
वर्ष साल महिला पुरुष पता ग्राम गांव गाँव तहसील जिला ज़िला मोबाइल फोन तारीख भर्ती छुट्टी निदान
पर्चा डिस्चार्ज सारांश संख्या पंजीकरण पति पत्नी पिता माता पुत्र पुत्री पास पीछे सामने मकान घर
वार्ड मंदिर मस्जिद अस्पताल डॉक्टर डॉ दवा खांसी दर्द पेट सिर संक्रमण पेशाब रक्तचाप उच्च
टाइप डायबिटीज़ डायबिटीज आईपीडी ओपीडी हुआ हुई रहा रही रहे गया गई लिए बाद पहले आज कल
"""
STOPWORDS = frozenset(_STOP.split())

HONORIFICS = frozenset("""ji sahab sahib saheb saab didi bhai bhaiya bhaiyya behen behenji bahen
bahenji amma amman chachu chacha chachi tai tau mausi bua dada dadi nana nani aunty uncle begum
जी साहब साहिब दीदी भाई भैया बहन बहनजी अम्मा चाचा चाची मौसी""".split())

# Honorifics or titles written before the name.
PREFIXES = frozenset("mr mrs ms miss shri sri smt kumari km master baby श्री श्रीमती सुश्री कुमारी".split())

# Name parts shared by many people; alone they neither identify nor link anyone.
GENERIC_NAME_PARTS = frozenset(phonetic(w) for w in
    "devi kumar kumari singh kaur bano begum khatun lal prasad md mohd mohammad ji bhai ben".split())

DOCTOR_TITLES = r"(?:Dr|DR|dr|Doctor|Prof|डॉ|डॉक्टर)"

MONTHS = {}
for _n, _names in enumerate([
    "january jan जनवरी", "february feb फरवरी फ़रवरी", "march mar मार्च", "april apr अप्रैल",
    "may मई", "june jun जून", "july jul जुलाई", "august aug अगस्त",
    "september sep sept सितंबर सितम्बर", "october oct अक्टूबर अक्तूबर",
    "november nov नवंबर नवम्बर", "december dec दिसंबर दिसम्बर"], 1):
    for _name in _names.split():
        MONTHS[_name] = _n
