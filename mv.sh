cd ..
npm run build -- --configuration production --base-href "/public_strautomata/"

cd dist
rm -rf media
rm -rf py
rm -rf __pycache__
rm -rf results

mv arena_fe/browser/* ./
