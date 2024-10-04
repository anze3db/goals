server {
    client_max_body_size 4M;

    server_name goals.pecar.me;

    location / {
      proxy_set_header Host $http_host;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection $connection_upgrade;
      proxy_redirect off;
      proxy_buffering off;
      proxy_pass http://gunicorn;
    }
}

  map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
  }

  upstream gunicorn {
    server unix:///home/anze/projects/goals/goals.sock;
  }
 server {



    listen 0.0.0.0:80;

    server_name goals.pecar.me;
    return 404; # managed by Certbot


}
