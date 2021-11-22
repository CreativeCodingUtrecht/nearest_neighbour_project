# load libraries
if (!require("pacman"))
        install.packages("pacman")
pacman::p_load(tibble, tidyverse, tidygeocoder, ggmap, osmdata, sf)
# for more info see: https://cran.r-project.org/web/packages/tidygeocoder/vignettes/tidygeocoder.html

# load data
df <-
        read.csv(
                "https://ckan.dataplatform.nl/dataset/0b65235f-d8ca-4ebc-ac88-3ff732c564a9/resource/ea690d9a-d858-40f6-9b4d-39b5e739b879/download/vleermuisverblijfplaatsenutrecht.csv",
                header = TRUE,
                sep = ","
        )

# tidy input file
address <- df %>%
        mutate(country = "Netherlands") %>%
        dplyr::select(!c(Via.wie., Opmerkingen)) %>%
        rename(
                street = Adres,
                city = Wijk.Dorp,
                type = Soort.vleermuis,
                number = Aantallen,
                function_bat = Functie,
        ) %>%
        filter(number != "??",
               number != "",
               number != "3-Jan") %>%
        mutate(number = str_replace(number, ">", "")) %>%
        mutate(number = as.numeric(number))

# perform geosearch with cleaned up file
geo_address <- address %>%
        tidygeocoder::geocode(
                street = street,
                city = city,
                country = country,
                lat = "lat",
                long = "lon",
                method = "osm",
                verbose = TRUE
        )

# save file for visualization in PowerBI
write_csv(geo_address, "bats.csv")

# get map for Utrecht
map <- get_map(getbb("Utrecht"), maptype = "toner-lines")

# plot map with geodata points
ggmap(map, 
      extent = "normal") + 
        geom_point(data = geo_address,
                   inherit.aes = T,
                   colour = "#238443",
                   fill = "#004529",
                   alpha = .5,
                   size = 5,
                   shape = 21) + 
        theme_void() 


