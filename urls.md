# apply tasks
curl -i -H 'Content-Type: application/json' -X POST --data-binary '{"action":"commit","pkgname":"dde-session-ui","reponame":"dde"}' http://127.0.0.1:5000/api/task/apply

# initial repo
curl -i -X POST -F "reponame=dde" -F "config=@config/default.repo.json" http://127.0.0.1:5000/api/repo/create

# create release-candidate division repo
curl -i -H 'Content-Type: application/json' -X POST --data-binary '{"action":"create","division":"3302","reponame":"dde", "baserepo":"release-candidate"}' http://127.0.0.1:5000/api/repo/division
