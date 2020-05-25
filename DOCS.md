# Domains

## Subdomains

Each blog has a subdomain set by the user eg: herman.bearblog.dev
When the subdomain is created or changed, give up to 5 minutes for the DNS records to propagate. 

## Custom Domains

To create a custom domain for your blog you'll have to register a domain with a domain registrar such as [NameCheap](https://namecheap.com).
Once you have a domain registered, add the following DNS record:

|Type|Name|Content|TTL|
|---|---|---|---|
|CNAME|{your domain or subdomain}|{user subdomain}.bearblog.dev|3600|

Back in the bearblog dashboard, add the domain to the Custom Domain field. 

## Contributing and contact

This project is free to use. To contribute to the codebase, open a PR.

To contribute to server fees, get in touch with [me](mailto:hfbmartinus@gmail.com)