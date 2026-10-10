import zipfile,xml.etree.ElementTree as E,copy
from pathlib import Path
D=Path(__file__).parent;p=D/'Midterm-Presentation.pptx'
z=zipfile.ZipFile(p); f={n:z.read(n) for n in z.namelist()}
P='http://schemas.openxmlformats.org/presentationml/2006/main';A='http://schemas.openxmlformats.org/drawingml/2006/main';R='http://schemas.openxmlformats.org/officeDocument/2006/relationships';K='http://schemas.openxmlformats.org/package/2006/relationships'
ns={'p':P,'a':A}
for k,v in [('p',P),('a',A),('r',R)]:E.register_namespace(k,v)
root=E.fromstring(f['ppt/slides/slide1.xml']);tree=root.find('p:cSld/p:spTree',ns)
pic=E.fromstring(f'<p:pic xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:nvPicPr><p:cNvPr id="900" name="AI-generated storyboard illustration"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rIdIllustration"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="5100000" y="2700000"/><a:ext cx="6700000" cy="2233333"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')
tree.append(pic)
sh=copy.deepcopy(tree.findall('p:sp',ns)[1])
sh.find('p:nvSpPr/p:cNvPr',ns).set('id','901');nv=sh.find('p:nvSpPr/p:nvPr',ns);nv.clear()
xf=sh.find('p:spPr/a:xfrm',ns);xf.find('a:off',ns).attrib.update({'x':'5100000','y':'5100000'});xf.find('a:ext',ns).attrib.update({'cx':'6700000','cy':'500000'})
tx=sh.find('p:txBody',ns)
for para in tx.findall('a:p',ns):tx.remove(para)
pa=E.SubElement(tx,'{'+A+'}p');r=E.SubElement(pa,'{'+A+'}r');rp=E.SubElement(r,'{'+A+'}rPr',{'sz':'1200'})
E.SubElement(E.SubElement(rp,'{'+A+'}solidFill'),'{'+A+'}srgbClr',{'val':'666666'});E.SubElement(r,'{'+A+'}t').text='AI-generated story illustration, not a prototype photograph'
tree.append(sh)
rel=E.fromstring(f['ppt/slides/_rels/slide1.xml.rels']);E.SubElement(rel,'{'+K+'}Relationship',{'Id':'rIdIllustration','Type':R+'/image','Target':'../media/midterm-story.png'})
f['ppt/media/midterm-story.png']=Path('user-study/story-survey-v2/assets/home-triptych.png').read_bytes()
f['ppt/slides/slide1.xml']=E.tostring(root,encoding='utf-8',xml_declaration=True);f['ppt/slides/_rels/slide1.xml.rels']=E.tostring(rel,encoding='utf-8',xml_declaration=True)
with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as out:
 for n,b in f.items():out.writestr(n,b)
print('Added existing storyboard illustration with disclosure.')
