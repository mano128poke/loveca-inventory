import os,re,json,time,requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
BASE="https://llofficial-cardgame.com/cardlist/searchresults/"
S=requests.Session();S.headers["User-Agent"]="Mozilla/5.0 LovecaInventorySync/1.0"
def page(n):
    u=BASE+"?view=text&sort=new"+("" if n==1 else "&page="+str(n))
    r=S.get(u,timeout=30);r.raise_for_status();return BeautifulSoup(r.text,"html.parser")
def main():
    out={}
    for n in range(1,301):
        soup=page(n); found=0
        for b in soup.select("article,li,.searchresults__item,.card-list-item"):
            t=b.get_text(" ",strip=True); m=re.search(r"カード番号\s*([A-Za-z0-9!+\-_.]+)",t)
            if not m: continue
            cid=m.group(1); found+=1
            def val(label,nexts):
                pat=label+r"\s*(.*?)\s*(?="+nexts+r"|$)"
                x=re.search(pat,t);return x.group(1).strip() if x else ""
            im=b.find("img"); img=urljoin(BASE,im.get("src")) if im and im.get("src") else ""
            name=next((x.get_text(" ",strip=True) for x in b.select("h2,h3,h4,.name,.card-name") if x.get_text(strip=True)!="詳しく見る"),"")
            out[cid]={"id":cid,"name":name,"product":val("収録商品","カードタイプ|作品名|参加ユニット|レアリティ|カード番号"),"kind":val("カードタイプ","作品名|参加ユニット|レアリティ|カード番号"),"school":val("作品名","参加ユニット|レアリティ|カード番号"),"unit":val("参加ユニット","レアリティ|カード番号"),"rarity":val("レアリティ","カード番号"),"image":img,"required":1}
        print(n,found,len(out))
        if n>1 and found==0: break
        time.sleep(.15)
    cards=sorted(out.values(),key=lambda x:x["id"])
    if len(cards)<2000: raise RuntimeError(f"Safety stop: only {len(cards)} cards found")
    os.makedirs("data",exist_ok=True)
    json.dump(cards,open("data/cards.json","w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print("WROTE",len(cards))
if __name__=="__main__": main()
